const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const setupBtn = document.getElementById('setupBtn');
const cleanupBtn = document.getElementById('cleanupBtn');
const statusLabel = document.getElementById('statusLabel');
let connecting = false;

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
    e.preventDefault(); // 入力させない(後で変更)
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