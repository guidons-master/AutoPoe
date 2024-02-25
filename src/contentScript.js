'use strict';
import TurndownService from 'turndown';

(function() {
  let length, response, lastText = '', buffer = '';
  const inputEvent = new Event('input', { bubbles: true });
  const turndownService = new TurndownService({ codeBlockStyle: 'fenced' });

  const sendMessage = function(message) {
    let input = document.querySelector("textarea");
    let botton = document.querySelector('button[class*="ChatMessageInputContainer_sendButton"]');
    if (!input || !botton) {
      chrome.runtime.sendMessage({ type: 'ERROR' });
      return false;
    }
    input.value = message;
    input.dispatchEvent(inputEvent);
    setTimeout(() => botton.click(), 100);
    return true;
  }

  window.onload = () => chrome.runtime.sendMessage({ type: 'READY' });

  MutationObserver = window.MutationObserver || window.WebKitMutationObserver;
  let observer = new MutationObserver(function(mutations, observer) {
    response || (response = document.querySelectorAll('div[class*="ChatMessage_chatMessage"] div[class*="Markdown_markdownContainer"]')[length + 1]);
    if (response) {
      response.querySelectorAll('div[class*="MarkdownCodeBlock_codeHeader"]').forEach(e => e.remove());
      let text = turndownService.turndown(response.innerHTML).trimEnd();
      // text = text.replace(/(.+)\n\n复制\n\n```/g, '```$1');
      if (text.endsWith('```')) text = text.slice(0, -3).trimEnd();
      let newText = text.replace(lastText, '');
      buffer += newText;
      let msgDom = document.querySelector('div[class*="InfiniteScroll_container"] > div:last-child > div:nth-child(2)');
      if (msgDom.tagName === 'DIV' && msgDom.hasAttribute('data-complete'))
        if (msgDom.getAttribute('data-complete') !== 'true') {
          if (buffer.length > 10) {
            chrome.runtime.sendMessage({ type: 'RES', payload: buffer });
            buffer = '';
          }
          lastText = text;
          return;
        } else {
          chrome.runtime.sendMessage({ type: 'RES', payload: buffer });
          chrome.runtime.sendMessage({ type: 'END' });
        }
      else chrome.runtime.sendMessage({ type: 'ERROR' });
      observer.disconnect();
      buffer = lastText = '';
    }
  });

  chrome.runtime.onMessage.addListener((request, _, sendResponse) => {
    if (request.type.endsWith('SEND')) {
      if (request.type === 'SEND' && request.payload.model !== document.querySelector('div[class*="ChatHeader_subText"]')?.innerText) {
        chrome.runtime.sendMessage({ type: 'URL', payload: request.payload });
        return;
      }
      length = document.querySelectorAll('div[class*="ChatMessage_chatMessage"] div[class*="Markdown_markdownContainer"]')?.length;
      response = null;
      if (sendMessage(request.payload.message))
        observer.observe(document.body, {
          subtree: true,
          attributes: true,
          characterData: true
        });
    }
    sendResponse({});
    return true;
  });
})();