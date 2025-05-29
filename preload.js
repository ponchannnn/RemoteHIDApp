const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('API', {
  connect: (ip, port) => ipcRenderer.invoke('connect', { ip, port }),
  sendKey: (keyEvent) => ipcRenderer.send('send-key', keyEvent),
  disconnect: () => ipcRenderer.send('disconnect'),
  sendCommand: (cmd) => ipcRenderer.send('send-command', cmd),
  sendMouse: (x, y, left = 0, right = 0, center = 0, side1 = 0, side2 = 0, wheel = 0) => {
    ipcRenderer.send('send-mouse', { x, y, left, right, center, side1, side2, wheel });
  },
});