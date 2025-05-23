const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('API', {
  connect: (ip, port) => ipcRenderer.invoke('connect', { ip, port }),
  sendKey: (keyEvent) => ipcRenderer.send('send-key', keyEvent),
  disconnect: () => ipcRenderer.send('disconnect'),
  sendCommand: (cmd) => ipcRenderer.send('send-command', cmd)
});