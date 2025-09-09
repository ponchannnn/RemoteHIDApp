const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const setupBtn = document.getElementById('setupBtn');
const cleanupBtn = document.getElementById('cleanupBtn');
const toolbar = document.querySelector('.toolbar');
const videoArea = document.getElementById('videoArea');
const webrtcVideo = document.getElementById('webrtcVideo');
const webrtcAudio = document.getElementById('webrtcAudio');
const videoStartBtn = document.getElementById('videoStartBtn');
const videoStopBtn = document.getElementById('videoStopBtn');
const audioDeviceSelect = document.getElementById('audioDeviceSelect');
const videoDeviceSelect = document.getElementById('videoDeviceSelect');
const micStartBtn = document.getElementById('micStartBtn');
const micStopBtn = document.getElementById('micStopBtn');
const statusLabel = document.getElementById('statusLabel');

const BASE_WIDTH = 320;
const BASE_HEIGHT = 240;
const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

let connecting = false;
let mouseX = webrtcVideo.width / 2;
let mouseY = webrtcVideo.height / 2;
let mouseButtons = { left: 0, right: 0, center: 0, side1: 0, side2: 0 };

let connectStatus = "未接続";
let micStatus = "OFF";
let videoStatus = "OFF";
let usbStatus = "";
let errorStatus = "";

let pc = null;
let wantVideo = false;
let wantAudio = false;

connectBtn.addEventListener('click', async () => {
  if (connecting) return;
  connecting = true;
  connectBtn.disabled = true;
  connectBtn.textContent = '接続中...';
  connectStatus = '🔄 接続中...';
  statusLabel.textContent = connectStatus;

  const ip = document.getElementById('ip').value;
  const port = Number(document.getElementById('port').value);
  const result = await window.API.connect(ip, port);

  connecting = false;
  if (result && result.connected) {
    connectBtn.textContent = '接続済み';
    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    connectStatus = '✅ 接続済み';
    // オーディオデバイスリストをセット
    audioDeviceSelect.innerHTML = '<option value="">オーディオデバイス選択</option>';
    if (Array.isArray(result.audioDevices)) {
      result.audioDevices.forEach(dev => {
        const opt = document.createElement('option');
        opt.value = dev.index;
        opt.textContent = `${dev.index}: ${dev.name} (${dev.max_input_channels}ch)`;
        audioDeviceSelect.appendChild(opt);
      });
      audioDeviceSelect.disabled = false;
    } else {
      audioDeviceSelect.disabled = true;
    }
    // ビデオデバイスリストをセット
    videoDeviceSelect.innerHTML = '<option value="">ビデオデバイス選択</option>';
    if (Array.isArray(result.videoDevices)) {
      result.videoDevices.forEach(dev => {
        const opt = document.createElement('option');
        opt.value = dev.index;
        opt.textContent = `${dev.index}: ${dev.name}`;
        videoDeviceSelect.appendChild(opt);
      });
      videoDeviceSelect.disabled = false;
    } else {
      videoDeviceSelect.disabled = true;
    }
    updateStatusLabel();
  } else {
    connectBtn.textContent = '接続';
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
    connectStatus = '❌ 接続失敗';
    statusLabel.textContent = connectStatus;
    audioDeviceSelect.innerHTML = '<option value="">オーディオデバイス選択</option>';
    audioDeviceSelect.disabled = true;
    videoDeviceSelect.innerHTML = '<option value="">ビデオデバイス選択</option>';
    videoDeviceSelect.disabled = true;
    alert('接続失敗');
  }
});

setupBtn.addEventListener('click', () => {
  window.API.usbSetup();
});
cleanupBtn.addEventListener('click', () => {
  window.API.usbCleanup();
});

disconnectBtn.addEventListener('click', () => {
  window.API.disconnect();
});

videoStartBtn.onclick = () => {
  const selectedDevice = videoDeviceSelect.value;
  if (!selectedDevice) {
    alert('ビデオデバイスを選択してください');
    return;
  }
  window.API.videoStart();
  wantVideo = true;
  videoStartBtn.disabled = true;
  videoStopBtn.disabled = false;
};

videoStopBtn.onclick = () => {
  blackoutVideo();
  window.API.videoStop();
  wantVideo = false;
  if (!wantVideo && !wantAudio && pc) {
    pc.close();
    pc = null;
  }
  videoStartBtn.disabled = false;
  videoStopBtn.disabled = true;
};

micStartBtn.onclick = () => {
  const selectedDevice = audioDeviceSelect.value;
  if (!selectedDevice) {
    alert('オーディオデバイスを選択してください');
    return;
  }
  micStartBtn.disabled = true;
  micStopBtn.disabled = false;
  window.API.micStart(Number(selectedDevice));
  wantAudio = true;
  webrtcAudio.play().catch(e => {
    console.warn("Pre-play failed, this is expected on first interaction.", e);
  });
};

micStopBtn.onclick = () => {
  window.API.micStop();
  wantAudio = false;
  if (!wantVideo && !wantAudio && pc) {
    pc.close();
    pc = null;
  }
  micStartBtn.disabled = false;
  micStopBtn.disabled = true;
};

document.addEventListener('keydown', (e) => {
    const keyEvent = {
        key: e.key,
        code: e.code,
        ctrl: e.ctrlKey,
        shift: e.shiftKey,
        alt: e.altKey,
        meta: e.metaKey
    };
    window.API.sendKey(keyEvent);
});



// マウス移動（ホバー）
webrtcVideo.addEventListener('mousemove', (e) => {
  sendMouseWithState(e);
});

webrtcVideo.addEventListener('mousedown', (e) => {
  if (e.button === 0) mouseButtons.left = 1;
  if (e.button === 2) mouseButtons.right = 1;
  if (e.button === 1) mouseButtons.center = 1;
  if (e.button === 3) mouseButtons.side1 = 1;
  if (e.button === 4) mouseButtons.side2 = 1;
  sendMouseWithState(e);
});

webrtcVideo.addEventListener('mouseup', (e) => {
  if (e.button === 0) mouseButtons.left = 0;
  if (e.button === 2) mouseButtons.right = 0;
  if (e.button === 1) mouseButtons.center = 0;
  if (e.button === 3) mouseButtons.side1 = 0;
  if (e.button === 4) mouseButtons.side2 = 0;
  sendMouseWithState(e);
});

// スクロール（ホイール）
webrtcVideo.addEventListener('wheel', (e) => {
  const rect = webrtcVideo.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  const wheel = Math.max(-127, Math.min(127, Math.round(-e.deltaY)));
  const hwheel = Math.max(-127, Math.min(127, Math.round(e.deltaX)));
  window.API.sendMouse(x, y, mouseButtons.left, mouseButtons.right, mouseButtons.center, mouseButtons.side1, mouseButtons.side2, wheel, hwheel);
  e.preventDefault();
});

webrtcVideo.addEventListener('contextmenu', (e) => e.preventDefault());

function sendMouseWithState(e) {
  const rect = webrtcVideo.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  window.API.sendMouse(x, y, mouseButtons.left, mouseButtons.right, mouseButtons.center, mouseButtons.side1, mouseButtons.side2, 0, 0);
}

function resizeVideoToWindow() {
  const toolbarHeight = toolbar ? toolbar.offsetHeight : 0;
  const winW = window.innerWidth;
  const winH = window.innerHeight;
  const availableH = winH - toolbarHeight - 10;
  const aspect = 16 / 9;
  let videoW = winW - 4;
  let videoH = (winW - 4) / aspect;
  if (videoH > availableH) {
    videoH = availableH - 4;
    videoW = (availableH - 2) * aspect;
  }
  videoArea.style.width = videoW + "px";
  videoArea.style.height = videoH + "px";
}
window.addEventListener('resize', resizeVideoToWindow);
resizeVideoToWindow();

window.API.onWebRTCSignal(async (msg) => {
  if (!pc) return;
  if (msg.type === 'answer') {
    await pc.setRemoteDescription({ type: 'answer', sdp: msg.sdp });
  } else if (msg.type === 'ice') {
    await pc.addIceCandidate({
      candidate: msg.candidate,
      sdpMid: msg.sdpMid,
      sdpMLineIndex: msg.sdpMLineIndex
    });
  }
});

async function startWebRTC() {
  if (pc) pc.close();
  pc = new RTCPeerConnection();

  if (wantVideo) {
    pc.addTransceiver('video', { direction: 'recvonly' });
  }
  if (wantAudio) {
    pc.addTransceiver('audio', { direction: 'recvonly' });
  }

  pc.ontrack = (event) => {
    console.log("ontrack event kind:", event.track.kind);
    if (event.track.kind === 'video') {
      console.log("video track received");
      console.log("video tracks:", event.streams[0].getVideoTracks().length);
      webrtcVideo.srcObject = event.streams[0];
      webrtcVideo.muted = true;
      webrtcVideo.autoplay = true;
      webrtcVideo.play().catch(e => console.error('video play error', e));
    } else if (event.track.kind === 'audio') {
      webrtcVideo.srcObject = event.streams[0];
      webrtcVideo.muted = false;
      webrtcVideo.autoplay = true;
      webrtcVideo.play().catch(e => console.error('audio play error', e));
    }
  };
  pc.onicecandidate = (event) => {
    if (event.candidate) {
      window.API.sendWebRTCSignal({
        type: 'ice',
        candidate: event.candidate.candidate,
        sdpMid: event.candidate.sdpMid,
        sdpMLineIndex: event.candidate.sdpMLineIndex
      });
    }
  };
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  window.API.sendWebRTCSignal({
    type: 'offer',
    sdp: offer.sdp
  });
}

webrtcVideo.addEventListener('error', e => console.error('video error', e));
webrtcVideo.addEventListener('loadeddata', () => console.log('video loadeddata'));
webrtcVideo.addEventListener('playing', () => console.log('video playing'));

window.API.onAudioStatus((msg) => {
  if (msg === "STARTED") {
    micStartBtn.disabled = true;
    micStopBtn.disabled = false;
    micStatus = "ON";
    startWebRTC();
  } else if (msg === "STOPPED") {
    micStartBtn.disabled = false;
    micStopBtn.disabled = true;
    micStatus = "OFF";
  }
  updateStatusLabel();
});

window.API.onVideoStatus((msg) => {
  if (msg === "STARTED") {
    videoStartBtn.disabled = true;
    videoStopBtn.disabled = false;
    videoStatus = "ON";
    startWebRTC();
  } else if (msg === "STOPPED") {
    videoStartBtn.disabled = false;
    videoStopBtn.disabled = true;
    videoStatus = "OFF";
  } else if (msg === "ALREADY_ACTIVE") {
    videoStatus = "すでにON";
  } else if (msg === "NOT_ACTIVE") {
    videoStatus = "OFF";
  }
  updateStatusLabel();
});

window.API.onErrorMessage((msg) => {
  errorStatus = msg;
  updateStatusLabel();
});

window.API.onUsbMessage((msg) => {
  usbStatus = msg;
  updateStatusLabel();
});

window.API.onDisconnect(() => {
  disconnectedStatus();
});

function disconnectedStatus() {
  if (pc) {
    pc.close();
    pc = null;
  }
  blackoutVideo();
  connectStatus = "未接続";
  micStatus = "OFF";
  videoStatus = "OFF";
  usbStatus = "";
  errorStatus = "";
  wantVideo = false;
  wantAudio = false;
  connectBtn.disabled = false;
  disconnectBtn.disabled = true;
  micStartBtn.disabled = false;
  micStopBtn.disabled = true;
  videoStartBtn.disabled = false;
  videoStopBtn.disabled = true;
  
  audioDeviceSelect.innerHTML = '<option value="">オーディオデバイス選択</option>';
  videoDeviceSelect.innerHTML = '<option value="">ビデオデバイス選択</option>';
  audioDeviceSelect.disabled = true;
  videoDeviceSelect.disabled = true;
  updateStatusLabel();
}

function updateStatusLabel() {
  let status = `接続状態: ${connectStatus}`;
  status += `マイク:${micStatus} ビデオ:${videoStatus}`;
  if (usbStatus) status += ` USB:${usbStatus}`;
  if (errorStatus) status += ` エラー:${errorStatus}`;
  statusLabel.textContent = status;
}

function blackoutVideo() {
  webrtcVideo.srcObject = null;
  webrtcVideo.pause();
  webrtcVideo.load();
}