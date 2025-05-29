const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const setupBtn = document.getElementById('setupBtn');
const cleanupBtn = document.getElementById('cleanupBtn');
const statusLabel = document.getElementById('statusLabel');
const canvas = document.getElementById('mouseCanvas');
const ctx = canvas.getContext('2d');

let connecting = false;
let mouseX = canvas.width / 2;
let mouseY = canvas.height / 2;
let mouseButtons = { left: 0, right: 0, center: 0, side1: 0, side2: 0 };

connectBtn.addEventListener('click', async () => {
  if (connecting) return;
  connecting = true;
  connectBtn.disabled = true;
  connectBtn.textContent = '接続中...';
  statusLabel.textContent = '🔄 接続中...';

  const ip = document.getElementById('ip').value;
  const port = Number(document.getElementById('port').value);
  const result = await window.API.connect(ip, port);

  connecting = false;
  if (result) {
    connectBtn.textContent = '接続済み';
    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    statusLabel.textContent = '✅ 接続済み';
  } else {
    connectBtn.textContent = '接続';
    connectBtn.disabled = false;
    statusLabel.textContent = '❌ 接続失敗';
    alert('接続失敗');
  }
});

setupBtn.addEventListener('click', () => {
  window.API.sendCommand('CMD:ISTICKTOIT_USB');
});
cleanupBtn.addEventListener('click', () => {
  window.API.sendCommand('CMD:REMOVE_GADGET');
});

disconnectBtn.addEventListener('click', () => {
  window.API.disconnect && window.API.disconnect();
  connectBtn.textContent = '接続';
  connectBtn.disabled = false;
  disconnectBtn.disabled = true;
  statusLabel.textContent = '未接続';
});

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

function drawPointer() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.beginPath();
  ctx.arc(mouseX, mouseY, 8, 0, 2 * Math.PI);
  ctx.fillStyle = '#0984e3';
  ctx.fill();
}
drawPointer();

// マウス移動（ホバー）
canvas.addEventListener('mousemove', (e) => {
  sendMouseWithState(e);
});

canvas.addEventListener('mousedown', (e) => {
  console.log('mousedown', e.button);
  if (e.button === 0) mouseButtons.left = 1;
  if (e.button === 2) mouseButtons.right = 1;
  if (e.button === 1) mouseButtons.center = 1;
  if (e.button === 3) mouseButtons.side1 = 1;
  if (e.button === 4) mouseButtons.side2 = 1;
  sendMouseWithState(e);
});

canvas.addEventListener('mouseup', (e) => {
  if (e.button === 0) mouseButtons.left = 0;
  if (e.button === 2) mouseButtons.right = 0;
  if (e.button === 1) mouseButtons.center = 0;
  if (e.button === 3) mouseButtons.side1 = 0;
  if (e.button === 4) mouseButtons.side2 = 0;
  sendMouseWithState(e);
});

// スクロール（ホイール）
canvas.addEventListener('wheel', (e) => {
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  const wheel = Math.max(-127, Math.min(127, Math.round(-e.deltaY)));
  const hwheel = Math.max(-127, Math.min(127, Math.round(e.deltaX)));
  window.API.sendMouse(x, y, mouseButtons.left, mouseButtons.right, mouseButtons.center, mouseButtons.side1, mouseButtons.side2, wheel, hwheel);
  e.preventDefault();
});

canvas.addEventListener('contextmenu', (e) => e.preventDefault());

function sendMouseWithState(e) {
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  drawPointer();
  window.API.sendMouse(x, y, mouseButtons.left, mouseButtons.right, mouseButtons.center, mouseButtons.side1, mouseButtons.side2, 0, 0);
}

function resizeCanvasToDisplaySize() {
  const rect = canvas.getBoundingClientRect();
  if (canvas.width !== rect.width || canvas.height !== rect.height) {
    canvas.width = rect.width;
    canvas.height = rect.height;
  }
}
window.addEventListener('resize', resizeCanvasToDisplaySize);
resizeCanvasToDisplaySize();