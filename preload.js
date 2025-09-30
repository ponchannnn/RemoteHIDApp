const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('API', {
  connect: (ip, port) => ipcRenderer.invoke('connect', { ip, port }),
  sendKey: (keyEvent) => ipcRenderer.send('send-key', keyEvent),
  disconnect: () => ipcRenderer.send('disconnect'),
  restart: () => ipcRenderer.send('restart'),
  usbSetup: () => ipcRenderer.send('usb-setup'),
  usbCleanup: () => ipcRenderer.send('usb-cleanup'),
  videoStart: (deviceIndex) => ipcRenderer.send('video-start', deviceIndex),
  videoStop: () => ipcRenderer.send('video-stop'),
  micStart: (deviceIndex) => ipcRenderer.send('mic-start', deviceIndex),
  micStop: () => ipcRenderer.send('mic-stop'),
  clientMicStart: () => ipcRenderer.send('client-mic-start'),
  clientMicStop: () => ipcRenderer.send('client-mic-stop'),
  onDisconnect: (callback) => ipcRenderer.on('disconnect', callback),
  onWebRTCSignal: (callback) => ipcRenderer.on('webrtc-signal', (event, msg) => callback(msg)),
  sendWebRTCSignal: (msg) => {ipcRenderer.send('webrtc-signal', msg);},
  onAudioStatus: (callback) => ipcRenderer.on('audio-status', (event, msg) => callback(msg)),
  onVideoStatus: (callback) => ipcRenderer.on('video-status', (event, msg) => callback(msg)),
  onClientAudioStatus: (callback) => ipcRenderer.on('client-audio-status', (event, msg) => callback(msg)),
  onErrorMessage: (callback) => ipcRenderer.on('error-message', (event, msg) => callback(msg)),
  onUsbMessage: (callback) => ipcRenderer.on('usb-message', (event, msg) => callback(msg)),
  sendMouse: (x, y, left = 0, right = 0, center = 0, side1 = 0, side2 = 0, wheel = 0) => {
    ipcRenderer.send('send-mouse', { x, y, left, right, center, side1, side2, wheel });
  },
});