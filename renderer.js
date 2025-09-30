const connectBtn = document.getElementById('connectBtn');
const restartBtn = document.getElementById('restartBtn');
const setupBtn = document.getElementById('setupBtn');
const cleanupBtn = document.getElementById('cleanupBtn');
const toolbar = document.querySelector('.toolbar');
const videoArea = document.getElementById('videoArea');
const webrtcVideo = document.getElementById('webrtcVideo');
const webrtcAudio = document.getElementById('webrtcAudio');
const serverVideoBtn = document.getElementById('serverVideoBtn');
const audioDeviceSelect = document.getElementById('audioDeviceSelect');
const videoDeviceSelect = document.getElementById('videoDeviceSelect');
const clientMicSelect = document.getElementById('clientMicSelect');
const serverMicBtn = document.getElementById('serverMicBtn');
const clientMicBtn = document.getElementById('clientMicBtn');
const statusLabel = document.getElementById('statusLabel');

const BASE_WIDTH = 320;
const BASE_HEIGHT = 240;
const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

let connected = false;
let serverVideoActive = false;
let serverMicActive = false;

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

let clientMicUse = false;
let localStream = null;

connectBtn.addEventListener('click', async () => {
  if (connected) {
    window.API.disconnect();
    return;
  }

  connectBtn.disabled = true;
  connectBtn.textContent = '🔄 接続中...';
  connectStatus = '🔄 接続中...';
  statusLabel.textContent = connectStatus;

  const ip = document.getElementById('ip').value;
  const port = Number(document.getElementById('port').value);
  const result = await window.API.connect(ip, port);

  if (result && result.connected) {
    connected = true;
    connectBtn.textContent = '✅ 接続済み';
    connectBtn.disabled = false;
    restartBtn.disabled = false;
    setupBtn.disabled = false;
    cleanupBtn.disabled = false;
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
      serverMicBtn.disabled = false;
    } else {
      audioDeviceSelect.disabled = true;
      serverMicBtn.disabled = true;
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
      serverVideoBtn.disabled = false;
    } else {
      videoDeviceSelect.disabled = true;
      serverVideoBtn.disabled = true;
    }
    updateStatusLabel();
  } else {
    connectBtn.textContent = '接続';
    connectBtn.disabled = false;
    connectStatus = '❌ 接続失敗';
    statusLabel.textContent = connectStatus;
    audioDeviceSelect.innerHTML = '<option value="">オーディオデバイス選択</option>';
    audioDeviceSelect.disabled = true;
    videoDeviceSelect.innerHTML = '<option value="">ビデオデバイス選択</option>';
    videoDeviceSelect.disabled = true;
    alert('接続失敗');
  }
  setupMicrophoneSelection();
  clientMicBtn.disabled = false;
  clientMicSelect.disabled = false;
});

setupBtn.addEventListener('click', () => {
  window.API.usbSetup();
});
cleanupBtn.addEventListener('click', () => {
  window.API.usbCleanup();
});

restartBtn.addEventListener('click', () => {
  if (confirm("サーバーを再起動します。よろしいですか？")) {
    window.API.restart();
  }
});

serverVideoBtn.onclick = async () => {
  serverVideoBtn.disabled = true;
  if (!connected) {
    alert('サーバーに接続してください');
    serverVideoBtn.disabled = false;
    return;
  }

  if(!serverVideoActive) {
    const selectedDevice = videoDeviceSelect.value;
    if (!selectedDevice) {
      alert('ビデオデバイスを選択してください');
      serverVideoBtn.disabled = false;
      return;
    }
    serverVideoBtn.textContent = "🔄 ビデオ接続準備中...";
    window.API.videoStart(Number(selectedDevice));
    wantVideo = true;
  } else {
    serverVideoBtn.textContent = "🔄 ビデオ切断準備中...";
    blackoutVideo();
    window.API.videoStop();
    wantVideo = false;
    await updateConnection();
  }
};

serverMicBtn.onclick = async () => {
  serverMicBtn.disabled = true;
  if (!connected) {
    alert('サーバーに接続してください');
    serverMicBtn.disabled = false;
    return;
  }

  if (!serverMicActive) {
    const selectedDevice = audioDeviceSelect.value;
    if (!selectedDevice) {
      alert('オーディオデバイスを選択してください');
      serverMicBtn.disabled = false;
      return;
    }
    serverMicBtn.textContent = "🔄 マイク接続準備中...";
    window.API.micStart(Number(selectedDevice));
    wantAudio = true;
    webrtcAudio.play().catch(e => {
      console.warn("Pre-play failed, this is expected on first interaction.", e);
    });
  } else {
    serverMicBtn.textContent = "🔄 マイク切断準備中...";
    window.API.micStop();
    wantAudio = false;
    await updateConnection();
  }
};

clientMicBtn.onclick = async () => {
  clientMicBtn.disabled = true;
  if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
      localStream = null;
    }
  if (!clientMicUse) {
    clientMicBtn.textContent = "🔄 マイク取得中...";
    const selectedDeviceId = clientMicSelect.value;
    if (!selectedDeviceId) {
        alert("マイクが選択されていません。");
        clientMicBtn.disabled = false;
        clientMicBtn.textContent = "クライアントマイク";
        return;
    }
    const constraints = {
        audio: { deviceId: { exact: selectedDeviceId } },
        video: false
    };
    try {
        localStream = await navigator.mediaDevices.getUserMedia(constraints);
        clientMicBtn.textContent = "🔄 マイク接続中...";
        clientMicUse = true;
        window.API.clientMicStart();
        if (!pc) startWebRTC();
        await updateConnection();
    } catch (e) {
        alert("マイクの取得に失敗しました。");
        console.error("getUserMedia error:", e);
        clientMicBtn.disabled = false;
        clientMicBtn.textContent = "クライアントマイク";
        return;
    }
  } else {
    clientMicBtn.textContent = "🔄 マイク切断中...";
    clientMicUse = false;
    if (!wantVideo && !wantAudio && !clientMicUse && pc) {
      pc.close();
      pc = null;
    }
    window.API.clientMicStop();
  }
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

async function setupMicrophoneSelection() {
    clientMicSelect.innerHTML = '<option value="">オーディオデバイス検索中</option>';
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputDevices = devices.filter(device => device.kind === 'audioinput');

      if (audioInputDevices.length === 0) {
          clientMicSelect.innerHTML = '<option value="">オーディオデバイスが見つかりません</option>';
          clientMicSelect.disabled = true;
          return;
      }
      clientMicSelect.innerHTML = '';
      audioInputDevices.forEach(device => {
          const option = document.createElement('option');
          option.value = device.deviceId;
          option.textContent = device.label || `マイク ${clientMicSelect.length + 1}`;
          clientMicSelect.appendChild(option);
      });
      clientMicSelect.disabled = false;

    } catch (e) {
        alert("デバイス一覧の取得中にエラーが発生しました:" + e);
    }
}
setupMicrophoneSelection();

async function startWebRTC() {
  if (pc) pc.close();
  pc = new RTCPeerConnection();

  pc.ontrack = (event) => {
    if (event.track.kind === 'video') {
      webrtcVideo.srcObject = event.streams[0];
      webrtcVideo.autoplay = true;
      webrtcVideo.play().catch(e => console.error('video play error', e));
    } else if (event.track.kind === 'audio') {
      webrtcAudio.srcObject = event.streams[0];
      webrtcAudio.autoplay = true;
      webrtcAudio.play().catch(e => console.error('audio play error', e));
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
  pc.onconnectionstatechange = () => {
    if (pc) {
      console.log(`Connection state changed to: ${pc.connectionState}`);
      if (pc.connectionState === 'closed' || pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        pc.close();
        pc = null;
      }
    }
  };
}

async function updateConnection() {
    const audioTransceiver = pc.getTransceivers().find(t => t.receiver.track?.kind === 'audio' || t.sender.track?.kind === 'audio');

    let targetAudioDirection = 'inactive';
    if (wantAudio && clientMicUse) {
        targetAudioDirection = 'sendrecv';
    } else if (wantAudio && !clientMicUse) {
        targetAudioDirection = 'recvonly';
    } else if (!wantAudio && clientMicUse) {
        targetAudioDirection = 'sendonly';
    }

    if (!audioTransceiver && targetAudioDirection !== 'inactive') {
      console.log("Adding audio transceiver with direction:", targetAudioDirection);
        pc.addTransceiver('audio', { direction: targetAudioDirection });
        const audioSender = pc.getTransceivers().find(t => t.receiver.track?.kind === 'audio' || t.sender.track?.kind === 'audio')?.sender;
        if (targetAudioDirection === 'sendrecv' || targetAudioDirection === 'sendonly') {
          if (clientMicUse && localStream) {
            audioSender.replaceTrack(localStream.getAudioTracks()[0]);
            console.log("Replaced audio track in PeerConnection");
          }
        } else {
          if (audioSender?.track) {
            await audioSender.replaceTrack(null);
            localStream?.getTracks().forEach(t => t.stop());
            localStream = null;
            console.log("Removed audio track from PeerConnection");
          }
        }
    } else if (audioTransceiver && audioTransceiver.direction !== targetAudioDirection) {
        console.log("Changing audio transceiver direction to:", targetAudioDirection);
        audioTransceiver.direction = targetAudioDirection;
    }

    const videoTransceiver = pc.getTransceivers().find(t => t.receiver.track?.kind === 'video');
    const targetVideoDirection = wantVideo ? 'recvonly' : 'inactive';

    if (!videoTransceiver && targetVideoDirection !== 'inactive') {
      console.log("Adding video transceiver with direction:", targetVideoDirection);
        pc.addTransceiver('video', { direction: targetVideoDirection });
    } else if (videoTransceiver && videoTransceiver.direction !== targetVideoDirection) {
        console.log("Changing video transceiver direction to:", targetVideoDirection);
        videoTransceiver.direction = targetVideoDirection;
    }
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    window.API.sendWebRTCSignal({ type: 'offer', sdp: pc.localDescription.sdp });
}

webrtcVideo.addEventListener('error', e => console.error('video error', e));
webrtcVideo.addEventListener('loadeddata', () => console.log('video loadeddata'));
webrtcVideo.addEventListener('playing', () => console.log('video playing'));

window.API.onAudioStatus(async (msg) => {
  if (msg === "STARTED") {
    serverMicBtn.disabled = false;
    serverMicBtn.textContent = "✅ サーバーマイク接続済み";
    serverMicActive = true;
    micStatus = "ON";
  } else if ( msg === "STARTING"){
    serverMicBtn.disabled = true;
    serverMicBtn.textContent = "🔄 サーバーマイク接続中...";
    serverMicActive = true;
    micStatus = "STARTING";
    if (!pc) await startWebRTC();
    await updateConnection();
  } else if (msg === "STOPPING"){
    serverMicBtn.disabled = true;
    serverMicBtn.textContent = "🔄 サーバーマイク切断中...";
    serverMicActive = false;
    micStatus = "STOPPING";
  } else if (msg === "STOPPED") {
    serverMicBtn.disabled = false;
    serverMicBtn.textContent = "サーバーマイク";
    serverMicActive = false;
    micStatus = "OFF";
  }
  updateStatusLabel();
});

window.API.onVideoStatus(async (msg) => {
  if (msg === "STARTED") {
    serverVideoBtn.disabled = false;
    serverVideoBtn.textContent = "✅ サーバービデオ接続済み";
    serverVideoActive = true;
    videoStatus = "ON";
  } else if (msg === "STARTING"){
    serverVideoBtn.disabled = true;
    serverVideoBtn.textContent = "🔄 サーバービデオ接続中...";
    serverVideoActive = true;
    videoStatus = "STARTING";
    if (!pc) await startWebRTC();
    await updateConnection();
  } else if (msg === "STOPPED") {
    serverVideoBtn.disabled = false;
    serverVideoBtn.textContent = "サーバービデオ";
    serverVideoActive = false;
    videoStatus = "OFF";
  } else if (msg === "STOPPING"){
    serverVideoBtn.disabled = true;
    serverVideoBtn.textContent = "🔄 サーバービデオ切断中...";
    serverVideoActive = false;
    videoStatus = "STOPPING";
  } else if (msg === "ALREADY_ACTIVE") {
    videoStatus = "すでにON";
  } else if (msg === "NOT_ACTIVE") {
    videoStatus = "OFF";
  }
  updateStatusLabel();
});

window.API.onClientAudioStatus((msg) => {
  if (msg === "STARTED") {
    clientMicBtn.disabled = false;
    clientMicBtn.textContent = "✅ クライアントマイク接続済み";
    clientMicUse = true;
    if (!pc) startWebRTC();
  } else if (msg === "STARTING"){
    clientMicBtn.disabled = true;
    clientMicBtn.textContent = "🔄 クライアントマイク接続中...";
    clientMicUse = true;
  } else if (msg === "STOPPED") {
    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
      localStream = null;
    }
    clientMicUse = false;
    clientMicBtn.disabled = false;
    clientMicBtn.textContent = "クライアントマイク";
  }
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
  connected = false;
  connectBtn.textContent = "接続";
  connectStatus = "未接続";
  connectBtn.disabled = false;
  restartBtn.disabled = true;
  setupBtn.disabled = true;
  cleanupBtn.disabled = true;
  serverMicActive = false;
  serverMicBtn.textContent = "サーバーマイク";
  serverMicBtn.disabled = true;
  serverVideoActive = false;
  serverVideoBtn.textContent = "サーバービデオ";
  serverVideoBtn.disabled = true;
  clientMicBtn.textContent = "クライアントマイク";
  clientMicBtn.disabled = true;
  micStatus = "OFF";
  videoStatus = "OFF";
  usbStatus = "";
  errorStatus = "";
  wantVideo = false;
  wantAudio = false;
  clientMicUse = false;
  localStream = null;
  
  audioDeviceSelect.innerHTML = '<option value="">オーディオデバイス選択</option>';
  videoDeviceSelect.innerHTML = '<option value="">ビデオデバイス選択</option>';
  clientMicSelect.innerHTML = '<option value="">USBデバイス選択</option>';
  audioDeviceSelect.disabled = true;
  videoDeviceSelect.disabled = true;
  clientMicSelect.disabled = true;
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