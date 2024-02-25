import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key = "sk-no-key-required"
)

use_stream = True
completion = client.chat.completions.create(
    model="GPT-3.5-Turbo",
    messages=[
        {"role": "user", "content": "JS多态"},
    ], stream=use_stream
)

if completion.response.status_code == 200:
    if use_stream:
        for chunk in completion:
            print(chunk.choices[0].delta.content, end="")
    else:
        content = response.choices[0].message.content
        print(content)
else:
    print("Error: {}".format(completion.response.content))