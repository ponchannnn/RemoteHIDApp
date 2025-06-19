const { app, BrowserWindow, ipcMain } = require('electron');
const WebSocket = require('ws');
let ws = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 600,
    height: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: __dirname + '/preload.js'
    }
  });
  win.loadFile('public/index.html');
}

app.whenReady().then(createWindow);

// 接続要求
ipcMain.handle('connect', async (event, { ip, port }) => {
  return new Promise((resolve) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      resolve(true);
      return;
    }
    ws = new WebSocket(`ws://${ip}:${port}`);
    ws.on('open', () => resolve(true));
    ws.on('error', () => resolve(false));
    ws.on('close', () => { ws = null; });
    ws.on('message', (data) => { 
      if (Buffer.isBuffer(data)) {
        const win = BrowserWindow.getAllWindows()[0];
        if (win) win.webContents.send('video-frame', data);
      }});
    });
});

ipcMain.on('disconnect', () => {
  if (ws) {
    ws.close();
    ws = null;
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

ipcMain.on('send-command', (event, cmd) => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(cmd);
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
    ws = null;
  }
});


process.on('uncaughtException', (err) => {
  if (ws) {
    ws.close();
    ws = null;
  }
});