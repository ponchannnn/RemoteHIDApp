#!/usr/bin/env python3
# pip install aiortc opencv-python-headless numpy websockets sounddevice av
# sudo apt update
# sudo apt install python3-gi python3-gst-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-omx-rpi # RPi4以前のOMX、RPi5ではv4l2m2mが主
# sudo apt install libgstreamer1.0-dev libgstrtspserver-1.0-dev # 開発用ヘッダ等
# sudo apt install gstreamer1.0-v4l2 # Video4Linux2プラグイン
# sudo apt install libportaudio2 # PortAudioライブラリ（音声ストリーミング用）
# sudo pip install sounddevice # 音声ストリーミング用
import asyncio
import websockets
import threading
import sys
import termios
import tty
import json
import subprocess
import cv2 # OpenCV
import numpy as np
import struct
import time
import sounddevice as sd
import os
import re
import signal
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from fractions import Fraction
from av import AudioFrame
import logging

KEY_MAP = {
    'a': 4, 'b': 5, 'c': 6, 'd': 7, 'e': 8, 'f': 9, 'g': 10, 'h': 11, 'i': 12, 'j': 13,
    'k': 14, 'l': 15, 'm': 16, 'n': 17, 'o': 18, 'p': 19, 'q': 20, 'r': 21, 's': 22,
    't': 23, 'u': 24, 'v': 25, 'w': 26, 'x': 27, 'y': 28, 'z': 29,
    '1': 30, '2': 31, '3': 32, '4': 33, '5': 34, '6': 35, '7': 36, '8': 37, '9': 38, '0': 39,
    '-': 45, '^': 46, '@': 47, '[': 48, ']': 49, '\\': 50, ';': 51, ':': 52, ',': 54, '.': 55, '/': 56,
    '`': 53, '=': 46,
    ' ': 44, '\n': 40, 'Enter': 40,'Return': 40, 'Backspace': 42,
    'Tab': 43, 'Escape': 41, 'CapsLock': 57,
    'F1': 58, 'F2': 59, 'F3': 60, 'F4': 61, 'F5': 62, 'F6': 63, 'F7': 64, 'F8': 65, 'F9': 66, 'F10': 67, 'F11': 68, 'F12': 69,
    'PrintScreen': 70, 'ScrollLock': 71, 'Pause': 72, 'Insert': 73, 'Home': 74, 'PageUp': 75, 'Delete': 76, 'End': 77, 'PageDown': 78,
    'RightArrow': 79, 'ArrowRight': 79, 'LeftArrow': 80, 'ArrowLeft': 80, 'DownArrow': 81,'ArrowDown': 81, 'UpArrow': 82, 'ArrowUp': 82,
    'NumLock': 83, 'Keypad/': 84, 'Keypad*': 85, 'Keypad-': 86, 'Keypad+': 87, 'KeypadEnter': 88,
    'Keypad1': 89, 'Keypad2': 90, 'Keypad3': 91, 'Keypad4': 92, 'Keypad5': 93, 'Keypad6': 94, 'Keypad7': 95, 'Keypad8': 96, 'Keypad9': 97, 'Keypad0': 98, 'Keypad.': 99,
    'NonUS#': 100, 'NonUS\\': 100, 'Application': 101, 'Power': 102,
    'Zenkaku': 135, 'Backquote': 135, 'International2': 136, 'International3': 137, 'NonConvert': 137, 'International4': 138, 'Convert': 138, 'International5': 139,
    'LANG1': 144, 'Hiragana': 144, 'KanaMode': 144, 'LANG2': 145,
}

SHIFT_REQUIRED = {
    'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f', 'G': 'g', 'H': 'h', 'I': 'i', 'J': 'j', 'K': 'k', 'L': 'l', 'M': 'm',
    'N': 'n', 'O': 'o', 'P': 'p', 'Q': 'q', 'R': 'r', 'S': 's', 'T': 't', 'U': 'u', 'V': 'v', 'W': 'w', 'X': 'x', 'Y': 'y', 'Z': 'z',
    '!': '1', '"': '2', '#': '3', '$': '4', '%': '5', '&': '6', "'": '7', '(': '8', ')': '9', '_': '-', '+': ';', '*': ':', '{': '[', '}': ']',
    '|': '\\', '~': '^', '<': ',', '>': '.', '?': '/', '`': '@' # WindowsでのShift+@ (` `) は `0x34` (`) となるが、一般的なキーボードの挙動に合わせる
}


MODIFIER_MAP = {
    'ctrl': 0x01, 'shift': 0x02, 'alt': 0x04, 'gui': 0x08,
    'ctrl_r': 0x10, 'shift_r': 0x20, 'alt_r': 0x40, 'gui_r': 0x80
}
NULL_CHAR = chr(0)

active_websockets = set()
main_loop = None

# グローバル変数（映像送出制御用）
video_streaming_active = False
video_capture_device = 0 # キャプチャーデバイス番号 (例: /dev/video0)
jpeg_quality = 70 # JPEG品質 (0-100)
target_fps = 60 # 目標フレームレート

audio_input_device = None # 音声入力デバイス番号（Noneの場合はデフォルトデバイスを使用）
audio_streaming_active = False
gstreamer_proc = None

def write_report(report):
    try:
        with open('/dev/hidg0', 'rb+') as fd:
            fd.write(report.encode())
    except Exception as e:
        print(f"Error writing to /dev/hidg0: {e}", flush=True)

def write_mouse(report):
    try:
        with open('/dev/hidg1', 'rb+') as fd:
            fd.write(report)
    except Exception as e:
        print(f"Error writing to /dev/hidg1: {e}", flush=True)

def send_key_event(key_event):
    modifiers = 0
    if key_event.get('ctrl'):  modifiers |= MODIFIER_MAP['ctrl']
    if key_event.get('shift'): modifiers |= MODIFIER_MAP['shift']
    if key_event.get('alt'):   modifiers |= MODIFIER_MAP['alt']
    if key_event.get('meta'):  modifiers |= MODIFIER_MAP['gui']

    key_name = key_event.get('key')
    keycode = None

    if key_name in SHIFT_REQUIRED:
        modifiers |= MODIFIER_MAP['shift']
        base_char = SHIFT_REQUIRED[key_name]
        keycode = KEY_MAP.get(base_char.lower()) # 基本文字は小文字で検索
    elif key_name:
        keycode = KEY_MAP.get(key_name) or KEY_MAP.get(key_event.get('code'))


    if not keycode and (modifiers != 0) and key_event.get('isModifier'): # 修飾キー単独押下の場合
        # isModifierフラグはElectron側で、これが修飾キーのみのイベントであることを示す想定
        report = chr(modifiers) + NULL_CHAR*7
        write_report(report)
        # 修飾キー単独の場合、リリースはクライアント側からのkeyupイベントで行う
    elif keycode:
        report = chr(modifiers) + NULL_CHAR + chr(keycode) + NULL_CHAR*5
        write_report(report)
        # 通常キーの場合、押下後すぐにリリース（これはタイピングの動作）
        # もしキーを押しっぱなしにする場合は、クライアントからのkeyupイベントでリリースを送信
        if not key_event.get('isModifier'): # 通常キーのkeyupはここで処理 (長押し非対応の場合)
             write_report(NULL_CHAR*8) # キーリリース
    elif key_name == "keyup_release_all": # 特殊コマンドで全リリース
        write_report(NULL_CHAR*8)
    else:
        print(f"Unsupported key_event: {key_event}", flush=True)

def move_mouse(x_ratio, y_ratio, left=0, right=0, center=0, side1=0, side2=0, wheel=0, hwheel=0):
    abs_x = int(x_ratio * 32767)
    abs_y = int(y_ratio * 32767)
    wheel_val = max(-128, min(127, int(wheel)))
    hwheel_val = max(-128, min(127, int(hwheel)))
    buttons = (
        (left & 1) | ((right & 1) << 1) | ((center & 1) << 2) |
        ((side1 & 1) << 3) | ((side2 & 1) << 4)
    )
    report = bytes([
        buttons,
        abs_x & 0xFF, (abs_x >> 8) & 0xFF,
        abs_y & 0xFF, (abs_y >> 8) & 0xFF,
        wheel_val & 0xFF,
        hwheel_val & 0xFF
    ])
    write_mouse(report)

async def send_audio_device_list(websocket):
    devices = sd.query_devices()
    # 入力デバイスのみ
    input_devices = [
        {"index": i, "name": d["name"], "max_input_channels": d["max_input_channels"]}
        for i, d in enumerate(devices) if d["max_input_channels"] > 0
    ]
    await websocket.send("AUL:" + json.dumps(input_devices))

async def send_video_device_list(websocket):
    import glob
    available = []
    video_devs = sorted(glob.glob('/dev/video*'))
    for dev in video_devs:
        try:
            index = int(dev.replace('/dev/video', ''))
        except ValueError:
            continue
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            name = get_video_device_name(dev)
            available.append({"index": index, "name": name})
            cap.release()
    await websocket.send("VUL:" + json.dumps(available))

def get_video_device_name(dev):
    try:
        # v4l2-ctl --device=/dev/videoX --info で情報取得
        out = subprocess.check_output(['v4l2-ctl', '--device=' + dev, '--info'], encoding='utf-8')
        for line in out.splitlines():
            if 'Name' in line:
                return line.split(':', 1)[1].strip()
    except Exception:
        pass
    return dev  # 取得できなければファイル名

# --- WebRTC Video Track ---
class VideoStreamTrack(MediaStreamTrack):
    kind = "video"
    def __init__(self, device=0, width=1280, height=720, fps=60):

        super().__init__()
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None
        self._stopped = False

    def start(self):
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
        fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        print("Current FOURCC:", "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]), flush=True)

    def stop(self):
        print("Stopping video stream...", flush=True)
        if self.cap:
            self.cap.release()
            self.cap = None

    async def recv(self):
        if not self.cap:
            self.start()
        # print("Waiting for next timestamp...", flush=True)
        # pts, time_base = await self.next_timestamp()
        # print("Reading frame...", flush=True)
        ret, frame = await asyncio.to_thread(self.cap.read)
        if not ret:
            raise Exception("Camera read failed")
        frame = await asyncio.to_thread(cv2.cvtColor, frame, cv2.COLOR_BGR2RGB)
        from av import VideoFrame
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        # video_frame.pts = pts
        # video_frame.time_base = time_base
        return video_frame

# --- WebRTC Audio Track ---
class AudioStreamTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self, device=None, samplerate=16000, channels=2):
        super().__init__()
        self.device = device
        self.channels = channels
        device_info = sd.query_devices(device)
        self.samplerate = int(device_info['default_samplerate'])
        self.samples_per_frame = int(self.samplerate * 0.02)
        self.stream = None

        self._start_time = None
        self._timestamp = 0

        self.lock = asyncio.Lock()

    def start(self):
        print("Starting audio stream...", flush=True)
        try:
            self.stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, dtype='int16', device=self.device)
            self.stream.start()
        except Exception as e:
            print(f"Error starting audio stream: {e}", flush=True)
        self._start_time = time.time()

    async def stop(self):
        async with self.lock:
            if self.stream:
                await asyncio.to_thread(self.stream.stop)
                await asyncio.to_thread(self.stream.close)
                self.stream = None
                print("Audio stream successfully cleaned up.", flush=True)
        super().stop()

    async def recv(self):
        try:
            async with self.lock:
                if not self.stream:
                    self.start()
                data, _ = await asyncio.to_thread(self.stream.read, self.samples_per_frame)
            data_reshaped = data.reshape(1, -1)
            frame = AudioFrame.from_ndarray(
                data_reshaped, format="s16", layout="stereo" if self.channels == 2 else "mono"
            )
            frame.pts = self._timestamp
            frame.sample_rate = self.samplerate
            frame.time_base = Fraction(1, self.samplerate)
            self._timestamp += self.samples_per_frame
            return frame
        except Exception as e:
            print(f"Error receiving audio frame: {e}", flush=True)

# --- WebSocket Signaling Handler ---
async def signaling_handler(websocket):
    active_websockets.add(websocket)

    pc = None
    relay = MediaRelay()
    video_track = None
    audio_track = None
    video_device = 0
    audio_device = None
    video_active = False
    audio_active = False

    async def start_webrtc():
        nonlocal pc, video_track, audio_track, relay
        if video_track:
            video_track.stop()
            video_track = None
        if audio_track:
            await audio_track.stop()
            audio_track = None
        if pc:
            await pc.close()
        pc = RTCPeerConnection()
        if video_active:
            video_track = VideoStreamTrack(device=video_device)
            pc.addTrack(relay.subscribe(video_track))
        if audio_active:
            audio_track = AudioStreamTrack(device=audio_device)
            pc.addTrack(audio_track)

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate is not None:
                await websocket.send(json.dumps({
                    "type": "ice",
                    "candidate": candidate.to_sdp(),
                    "sdpMid": candidate.sdp_mid,
                    "sdpMLineIndex": candidate.sdp_mline_index
                }))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"RTC connection state: {pc.connectionState}", flush=True)


    async def stop_webrtc():
        print("stop_webrtc called", flush=True)
        nonlocal pc, video_track, audio_track
        if pc:
            await pc.close()
            pc = None
        if video_track:
            video_track.stop()
            video_track = None
        if audio_track:
            await audio_track.stop()
            audio_track = None

    try:
        async for message in websocket:
            # --- 制御コマンド ---
            if isinstance(message, str):
                if message.startswith("AUDIO:GET_DEVLIST"):
                    await send_audio_device_list(websocket)
                elif message.startswith("VIDEO:GET_DEVLIST"):
                    await send_video_device_list(websocket)
                elif message.startswith("AUDIO:ONSTART"):
                    parts = message.split(":")
                    if len(parts) >= 3:
                        try:
                            audio_device = int(parts[2])
                        except Exception:
                            audio_device = None
                    else:
                        audio_device = None
                    audio_active = True
                    await start_webrtc()
                    await websocket.send("AUM:STARTED")
                elif message.startswith("AUDIO:ONSTOP"):
                    audio_active = False
                    await stop_webrtc()
                    await websocket.send("AUM:STOPPED")
                elif message.startswith("VIDEO:ONSTART"):
                    parts = message.split(":")
                    if len(parts) >= 3:
                        try:
                            video_device = int(parts[2])
                        except Exception:
                            video_device = 0
                    else:
                        video_device = 0
                    video_active = True
                    await start_webrtc()
                    await websocket.send("VIM:STARTED")
                elif message.startswith("VIDEO:ONSTOP"):
                    video_active = False
                    await stop_webrtc()
                    await websocket.send("VIM:STOPPED")
                elif message.startswith("KEY:"):
                    try:
                        key_event = json.loads(message[4:])
                        send_key_event(key_event)
                    except Exception as e:
                        print(f"Error processing KEY event: {e}", flush=True)
                elif message.startswith("MOUSE:"):
                    try:
                        _, params = message.split(':', 1)
                        values = list(map(float, params.split(',')))
                        move_mouse(
                            values[0], values[1],
                            int(values[2]), int(values[3]), int(values[4]),
                            int(values[5]), int(values[6]),
                            int(values[7]), int(values[8])
                        )
                    except Exception as e:
                        print(f"Error processing MOUSE event: {e}", flush=True)
                elif message == "CMD:ISTICKTOIT_USB":
                    try:
                        script_path = os.path.expanduser('/usr/bin/isticktoit.usb')
                        subprocess.run(['sudo', 'bash', script_path], check=True, timeout=15)
                        await websocket.send('ISM:OK_ISTICKTOIT_USB')
                    except subprocess.CalledProcessError as e:
                        await websocket.send(f'ISM:ERR_ISTICKTOIT_USB_CALLED_PROCESS_ERROR:{e.stderr.decode() if e.stderr else e}')
                    except subprocess.TimeoutExpired:
                        await websocket.send('ISM:ERR_ISTICKTOIT_USB_TIMEOUT')
                    except FileNotFoundError:
                        await websocket.send('ISM:ERR_ISTICKTOIT_USB_NOT_FOUND')
                    except Exception as e:
                        await websocket.send(f'ISM:ERR_ISTICKTOIT_USB:{e}')
                
                elif message == "CMD:REMOVE_GADGET": # より安全なガジェット削除/無効化を検討
                    print("CMD:REMOVE_GADGET received. Attempting to remove USB gadget.", flush=True)
                    try:
                        # まずUDCからアンバインド
                        udc_path = '/sys/kernel/config/usb_gadget/isticktoit/UDC'
                        # isticktoitディレクトリが存在するか確認
                        if subprocess.run(['sudo', 'test', '-f', udc_path]).returncode == 0:
                             subprocess.run(['sudo', 'sh', '-c', f'echo "" > {udc_path}'], check=True, timeout=5)
                        # その後、設定ディレクトリを削除（オプション、アンバインドだけで十分な場合も）
                        # subprocess.run(['sudo', 'rm', '-rf', '/sys/kernel/config/usb_gadget/isticktoit'], check=True, timeout=5)
                        await websocket.send('ISM:OK_REMOVE_GADGET')
                    except Exception as e:
                        await websocket.send(f'ISM:ERR_REMOVE_GADGET:{e}')
                # --- WebRTCシグナリング ---
                else:
                    try:
                        msg = json.loads(message)
                        if msg["type"] == "offer":
                            if not pc:
                                await start_webrtc()
                            offer = RTCSessionDescription(sdp=msg["sdp"], type=msg["type"])
                            await pc.setRemoteDescription(offer)
                            answer = await pc.createAnswer()
                            await pc.setLocalDescription(answer)
                            await websocket.send(json.dumps({"type": "answer", "sdp": pc.localDescription.sdp}))
                        elif msg["type"] == "ice":
                            m = re.match(
                                r"candidate:(\d+) (\d+) (\w+) (\d+) ([\d\.a-fA-F:]+) (\d+) typ (\w+)(?: raddr ([\d\.a-fA-F:]+))?(?: rport (\d+))?(?: tcptype (\w+))?",
                                msg["candidate"]
                            )
                            if not m:
                                raise ValueError("Could not parse candidate: ")
                            foundation = m.group(1)
                            component = int(m.group(2))
                            protocol = m.group(3).lower()
                            priority = int(m.group(4))
                            ip = m.group(5)
                            port = int(m.group(6))
                            type_ = m.group(7)
                            relatedAddress = m.group(8)
                            relatedPort = int(m.group(9)) if m.group(9) else None
                            tcpType = m.group(10) if m.group(10) else None

                            from aiortc import RTCIceCandidate
                            candidate = RTCIceCandidate(
                                component=component,
                                foundation=foundation,
                                ip=ip,
                                port=port,
                                priority=priority,
                                protocol=protocol,
                                type=type_,
                                relatedAddress=relatedAddress,
                                relatedPort=relatedPort,
                                sdpMid=msg["sdpMid"],
                                sdpMLineIndex=msg["sdpMLineIndex"],
                                tcpType=tcpType
                            )
                            await pc.addIceCandidate(candidate)
                    except Exception as e:
                        print(f"WebRTC signaling error: {e}", flush=True)
            else:
                print(f"Received unexpected binary data: {len(message)} bytes", flush=True)
    finally:
        await stop_webrtc()
        active_websockets.discard(websocket)

async def shutdown():
    print("Shutting down, closing websockets...", flush=True)
    await asyncio.gather(*(ws.close() for ws in list(active_websockets)), return_exceptions=True)
    for task in asyncio.all_tasks():
        if not task.done():
            task.cancel()

# --- WebSocket Server ---
async def main():
    logging.basicConfig(level=logging.DEBUG)
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    async with websockets.serve(signaling_handler, "0.0.0.0", 8765):
        print("WebRTC signaling server started on ws://0.0.0.0:8765")
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main())