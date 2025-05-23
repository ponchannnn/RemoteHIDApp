const { app, BrowserWindow, ipcMain } = require('electron');
const net = require('net');
let client = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 600,
    height: 400,
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
  return new Promise((resolve, reject) => {
    // すでに接続していたら一度切断
    if (client) {
      client.destroy();
      client = null;
    }
    client = net.createConnection({ host: ip, port: port || 5555 }, () => {
      resolve(true);
    });
    client.on('error', (err) => {
      resolve(false);
    });
  });
});

ipcMain.on('disconnect', () => {
  if (client) {
    client.destroy();
    client = null;
  }
});

ipcMain.on('send-command', (event, cmd) => {
  if (client) client.write(cmd + '\n');
});

// キー送信
ipcMain.on('send-key', (event, keyEvent) => {
  if (client) client.write(`KEY:${JSON.stringify(keyEvent)}\n`);
});

app.on('before-quit', () => {
  if (client) {
    client.destroy();
    client = null;
  }
});


process.on('uncaughtException', (err) => {
  if (client) {
    client.destroy();
    client = null;
  }

  console.error(err);
  app.quit();
});