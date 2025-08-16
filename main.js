const { app, BrowserWindow, ipcMain, Menu} = require('electron');
const WebSocket = require('ws');
let ws = null;

// アプリケーションメニューを定義する
const menuTemplate = [
    // { role: 'appMenu' } // macOS用
    // { role: 'fileMenu' }
    {
        label: 'Debug', // デバッグメニューを追加
        submenu: [
            {
                label: 'Open WebRTC Internals',
                click: async () => {
                    // 新しいウィンドウで webrtc-internals を開く
                    const debugWindow = new BrowserWindow({
                        width: 800,
                        height: 600,
                        title: 'WebRTC Internals'
                    });
                    debugWindow.loadURL('chrome://webrtc-internals');
                }
            },
            { role: 'toggleDevTools' } // 通常の開発者ツールを開くメニュー
        ]
    }
];

const menu = Menu.buildFromTemplate(menuTemplate);
Menu.setApplicationMenu(menu);

function createWindow() {
  const win = new BrowserWindow({
    width: 600,
    height: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,
      autoplayPolicy: 'no-user-gesture-required',
      preload: __dirname + '/preload.js'
    }
  });
  win.loadFile('public/index.html');
}

app.whenReady().then(createWindow);

// 接続要求
ipcMain.handle('connect', async (event, { ip, port }) => {
  function getDeviceList(command, header) {
    return new Promise((resolve) => {
      ws.send(command);
      ws.once('message', (data) => {
        let h = Buffer.isBuffer(data) ? data.slice(0, 4).toString() : data.slice(0, 4);
        if (h.startsWith(header)) {
          const json = Buffer.isBuffer(data) ? data.toString('utf8').slice(4) : data.slice(4);
          resolve(JSON.parse(json));
        } else {
          resolve([]);
        }
      });
    });
  }

  return new Promise((resolve) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      (async () => {
        const audioDevices = await getDeviceList('AUDIO:GET_DEVLIST', 'AUL:');
        const videoDevices = await getDeviceList('VIDEO:GET_DEVLIST', 'VUL:');
        resolve({ connected: true, audioDevices, videoDevices });
      })();
      return;
    }
    ws = new WebSocket(`ws://${ip}:${port}`);
    ws.on('open', async () => {
      const audioDevices = await getDeviceList('AUDIO:GET_DEVLIST', 'AUL:');
      const videoDevices = await getDeviceList('VIDEO:GET_DEVLIST', 'VUL:');
      resolve({ connected: true, audioDevices, videoDevices });
    });
    ws.on('error', () => resolve(false));
    ws.on('close', () => {
      ws = null;
      const win = BrowserWindow.getAllWindows()[0];
      win.webContents.send('disconnect');
    });
    ws.on('message', (data) => {
      const win = BrowserWindow.getAllWindows()[0];
      let header = "";
      if (Buffer.isBuffer(data)) {
        header = data.slice(0, 4).toString();
      } else if (typeof data === 'string') {
        header = data.slice(0, 4);
      }

      if (header === "AUL:") {
        // 音声デバイスリスト
        let json = Buffer.isBuffer(data) ? data.toString('utf8').slice(4) : data.slice(4);
        win.webContents.send('audio-device-list', JSON.parse(json));
      } else if (header === "VUL:") {
        // 映像デバイスリスト
        let json = Buffer.isBuffer(data) ? data.toString('utf8').slice(4) : data.slice(4);
        win.webContents.send('video-device-list', JSON.parse(json));
      } else if (header === "AUM:" || header === "VIM:" || header === "ERM:" || header === "ISM:") {
        // 状態やエラー通知
        let text = Buffer.isBuffer(data) ? data.toString('utf8').slice(4) : data.slice(4);
        if (header === "AUM:") {
          win.webContents.send('audio-status', text);
        } else if (header === "VIM:") {
          win.webContents.send('video-status', text);
        } else if (header === "ERM:") {
          win.webContents.send('error-message', text);
        } else if (header === "ISM:") {
          win.webContents.send('usb-message', text);
        }
      } else {
        // WebRTCシグナリング(JSON)の中継
        try {
          const msg = JSON.parse(Buffer.isBuffer(data) ? data.toString('utf8') : data);
          if (msg.type === "answer" || msg.type === "ice") {
            win.webContents.send('webrtc-signal', msg);
          }
        } catch (e) {}
      }
    });
    });
});

ipcMain.on('disconnect', () => {
  if (ws) {
    ws.close();
  }
});

ipcMain.on('get-audio-devices', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('AUDIO:GET_DEVLIST');
  }
});
ipcMain.on('get-video-devices', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('VIDEO:GET_DEVLIST');
  }
});

ipcMain.on('usb-setup', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('CMD:ISTICKTOIT_USB');
  }
});

ipcMain.on('usb-cleanup', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('CMD:REMOVE_GADGET');
  }
});

ipcMain.on('video-start', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('VIDEO:ONSTART');
  }
});
ipcMain.on('video-stop', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('VIDEO:ONSTOP');
  }
});

ipcMain.on('mic-start', (event, deviceIndex) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(`AUDIO:ONSTART:${deviceIndex}`);
  }
});
ipcMain.on('mic-stop', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('AUDIO:ONSTOP');
  }
});

ipcMain.on('webrtc-signal', (event, msg) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
});

// キー送信
ipcMain.on('send-key', (event, keyEvent) => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(`KEY:${JSON.stringify(keyEvent)}`);
});

ipcMain.on('send-mouse', (event, { x, y, left = 0, right = 0, center = 0, side1 = 0, side2 = 0, wheel = 0, hwheel = 0 }) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(`MOUSE:${x},${y},${left},${right},${center},${side1},${side2},${wheel},${hwheel}`);
  }
});

app.on('before-quit', () => {
  if (ws) {
    ws.close();
  }
});


process.on('uncaughtException', (err) => {
  if (ws) {
    ws.close();
  }
});