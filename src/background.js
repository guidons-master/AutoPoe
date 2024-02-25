'use strict';

let webSocket = null;
let reconnectIntervalId = null;
let resend = null;
const sign = new ArrayBuffer(1);
const view = new DataView(sign);

function connect() {
  webSocket = new WebSocket('ws://127.0.0.1:8765/ws');

  webSocket.onopen = (event) => {
    console.log('websocket open');
    keepAlive();
    if (reconnectIntervalId) {
      clearInterval(reconnectIntervalId);
      reconnectIntervalId = null;
    }
  };

  webSocket.onmessage = (event) => {
    console.log(`websocket received message: ${event.data}`);
    chrome.tabs.query({url: chrome.runtime.getManifest().content_scripts[0].matches[0]}, function(tabs) {
      for (let tab of tabs) {
        chrome.tabs.sendMessage(tab.id, {
          type: 'SEND',
          payload: JSON.parse(event.data)
        }, function(response) {});
        break;
      }
    });
  };

  webSocket.onclose = (event) => {
    console.log('websocket connection closed');
    webSocket = null;
    if (!reconnectIntervalId) {
      reconnectIntervalId = setInterval(connect, 5000);
    }
  };
}

function disconnect() {
  if (webSocket == null) {
    return;
  }
  webSocket.close();
}

function keepAlive() {
  const keepAliveIntervalId = setInterval(
    () => {
      if (webSocket) {
        view.setUint8(0, 0xff);
        webSocket.send(sign);
      } else {
        clearInterval(keepAliveIntervalId);
      }
    },
    20 * 1000 
  );
}

chrome.runtime.onMessage.addListener((request, _, sendResponse) => {
  switch (request.type) {
    case 'RES':
      webSocket?.send(request.payload);
      break;
    case 'END':
      view.setUint8(0, 0x00);
      webSocket?.send(sign);
      break;
    case 'ERROR':
      view.setUint8(0, 0x01);
      webSocket?.send(sign);
      break;
    case 'URL':
      chrome.tabs.query({url: chrome.runtime.getManifest().content_scripts[0].matches[0]}, function(tabs) {
        if (tabs.length) {
          chrome.tabs.update(tabs[0].id, {url: "https://poe.com/" + request.payload.model});
          resend = () => {
            chrome.tabs.query({url: chrome.runtime.getManifest().content_scripts[0].matches[0]}, function(tabs) {
              if (tabs.length) {
                chrome.tabs.sendMessage(tabs[0].id, {
                  type: 'RESEND',
                  payload: request.payload
                }, function(response) {});
              }
            });
          
          }
        }
      });
    case 'READY':
      resend && resend();
      resend = null;
      break;
  }

  sendResponse({});
  return true;
})

connect()