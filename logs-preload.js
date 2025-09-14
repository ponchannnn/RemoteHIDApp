const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('logAPI', {
    onLogStart: () => ipcRenderer.send('logs-start'),
    onLogStop: () => ipcRenderer.send('logs-stop'),
    onLogMessage: (callback) => ipcRenderer.on('log-message', (event, message) => callback(message))
});