import asyncio
import websockets as ws
from json import dumps 
from fastapi import FastAPI, WebSocket, HTTPException, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from typing_extensions import Literal
import time

class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "owner"
    root: Optional[str] = None
    parent: Optional[str] = None
    permission: Optional[list] = None


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard] = []


class FunctionCallResponse(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "function"]
    content: str = None
    name: Optional[str] = None
    function_call: Optional[FunctionCallResponse] = None


class DeltaMessage(BaseModel):
    role: Optional[Literal["user", "assistant", "system"]] = None
    content: Optional[str] = None
    function_call: Optional[FunctionCallResponse] = None


## for Embedding
class EmbeddingRequest(BaseModel):
    input: List[str]
    model: str


class CompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    data: list
    model: str
    object: str
    usage: CompletionUsage


# for ChatCompletionRequest

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens: Optional[int] = 0


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.8
    top_p: Optional[float] = 0.8
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    tools: Optional[Union[dict, List[dict]]] = None
    repetition_penalty: Optional[float] = 1.1


class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Literal["stop", "length", "function_call"]


class ChatCompletionResponseStreamChoice(BaseModel):
    delta: DeltaMessage
    finish_reason: Optional[Literal["stop", "length", "function_call"]]
    index: int


class ChatCompletionResponse(BaseModel):
    model: str
    id: str
    object: Literal["chat.completion", "chat.completion.chunk"]
    choices: List[Union[ChatCompletionResponseChoice, ChatCompletionResponseStreamChoice]]
    created: Optional[int] = Field(default_factory=lambda: int(time.time()))
    usage: Optional[UsageInfo] = None

EventSourceResponse.DEFAULT_PING_INTERVAL = 100

app = FastAPI()
llms = ModelList(
    data=[
        ModelCard(id="GPT-3.5-Turbo"),
        ModelCard(id="Assistant"),
        ModelCard(id="Code-Llama-70B-FW"),
        ModelCard(id="Gemini-Pro"),
        ModelCard(id="Web-Search"),
        ModelCard(id="Claude-instant"),
        ModelCard(id="ChatGPT"),
        ModelCard(id="Llama-2-7b"),
        ModelCard(id="Google-PaLM"),
        ModelCard(id="Llama-2-13b"),
        ModelCard(id="Claude-instant-100k"),
        ModelCard(id="Mistral-Medium"),
        ModelCard(id="Llama-2-70b-Groq"),
        ModelCard(id="RekaFlash"),
        ModelCard(id="Mixtral-8x7B-Chat"),
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

server, text_queue = None, None
websockets = set()

async def startup_event():
    global server, text_queue
    text_queue = asyncio.Queue()
    server = await ws.serve(handle, "localhost", 8765)

async def shutdown_event():
    server.close()
    await server.wait_closed()

app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)

async def handle(websocket, path):
    global websockets, text_queue
    websockets.add(websocket)
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                if message[0] == 0xff:
                    pass
                elif message[0] == 0x00:
                    text_queue.put_nowait(None)
                elif message[0] == 0x01:
                    text_queue.put_nowait(False)
                continue

            text_queue.put_nowait(message)
    finally:
        websockets.remove(websocket)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await handle(websocket, "/ws")

@app.get("/health")
async def health() -> Response:
    """Health check."""
    return Response(status_code=200)

@app.get("/v1/models", response_model=ModelList)
async def list_models():
    return llms

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(request: ChatCompletionRequest):
    if websockets.__len__() == 0:
        raise HTTPException(status_code=500, detail="ws connection not established")
    
    if len(request.messages) < 1 or request.messages[-1].role == "assistant":
        raise HTTPException(status_code=400, detail="Invalid request")

    if request.model not in [llm.id for llm in llms.data]:
        raise HTTPException(status_code=404, detail="model not found")

    for websocket in websockets:
        try:
            await asyncio.wait_for(websocket.send(
                '{ "model": "%s", "message": "%s" }' % (request.model, request.messages[-1].content)
            ), timeout=10.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="ws send timeout")
        break

    if request.stream:
        async def stream_gen():
            global text_queue
            while True:
                try: text = await asyncio.wait_for(text_queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    raise HTTPException(status_code=500, detail="Poe did not respond")

                print(text)
                if text is False: 
                    text_queue = asyncio.Queue()
                    raise HTTPException(status_code=500, detail="Poe not ready")

                message = DeltaMessage(
                    content=text if text is not None else "",
                    role="assistant",
                    function_call=None,
                )
                choice_data = ChatCompletionResponseStreamChoice(
                    index=0,
                    delta=message,
                    finish_reason=None if text is not None else "stop"
                )
                chunk = ChatCompletionResponse(
                    model=request.model,
                    id="",
                    choices=[choice_data],
                    created=int(time.time()),
                    object="chat.completion.chunk"
                )
                yield "{}".format(chunk.model_dump_json(exclude_unset=True))

                if text is None and text_queue.empty():
                    yield '[DONE]'
                    break

        return EventSourceResponse(stream_gen(), media_type="text/event-stream")
    
    global text_queue
    data = ''
    while True:
        text = await text_queue.get()
        if text is False: 
            text_queue = asyncio.Queue()
            raise HTTPException(status_code=500, detail="Poe not ready")
        elif text is None and text_queue.empty():
            break
        data += text

    message = ChatMessage(
        role="assistant",
        content=data,
        function_call=None,
    )

    choice_data = ChatCompletionResponseChoice(
        index=0,
        message=message,
        finish_reason="stop",
    )

    return ChatCompletionResponse(
        model=request.model,
        id="", 
        choices=[choice_data],
        object="chat.completion",
        usage=UsageInfo()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)