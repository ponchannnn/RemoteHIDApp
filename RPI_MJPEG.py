#!/usr/bin/env python3
# pip install aiortc opencv-python-headless numpy websockets sounddevice av
# sudo apt update
# sudo apt install python3-gi python3-gst-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-omx-rpi # RPi4以前のOMX、RPi5ではv4l2m2mが主
# sudo apt install libgstreamer1.0-dev libgstrtspserver-1.0-dev # 開発用ヘッダ等
# sudo apt install gstreamer1.0-v4l2 # Video4Linux2プラグイン
# sudo apt install libportaudio2 # PortAudioライブラリ（音声ストリーミング用）
# sudo pip install sounddevice # 音声ストリーミング用
# sudo pip install dotenv # 環境変数読み込み用
# sudo pip install aiohttp # Discord Webhook用

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
from aiortc.mediastreams import MediaStreamError
from fractions import Fraction
import av
from av import AudioFrame, VideoFrame
import logging
import aiohttp
from dotenv import load_dotenv
import socket

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

main_task = None
active_websockets = set()
main_loop = None

# グローバル変数（映像送出制御用）
video_streaming_class = None
video_capture_device = 0 # キャプチャーデバイス番号 (例: /dev/video0)
jpeg_quality = 70 # JPEG品質 (0-100)
target_fps = 60 # 目標フレームレート

audio_input_device = None # 音声入力デバイス番号（Noneの場合はデフォルトデバイスを使用）
audio_streaming_class = None
audio_streaming_samplerate = None
gstreamer_proc = None

def write_report(report):
    with open('/dev/hidg0', 'rb+') as fd:
            fd.write(report.encode())

def write_mouse(report):
    with open('/dev/hidg1', 'rb+') as fd:
        fd.write(report)

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
    def __init__(self, width=1280, height=720, fps=30):

        super().__init__()
        self.device = video_capture_device
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None

        self.pts_increment = 90000 / self.fps
        self.frame_count = 0

        self.lock = asyncio.Lock()

    def start(self):
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
        self.start_time = time.time()

    def stop(self):
        asyncio.create_task(self._async_stop())
        super().stop()

    async def _async_stop(self):
        async with self.lock:
            if self.cap:
                await asyncio.to_thread(self.cap.release)
                self.cap = None
        super().stop()

    async def recv(self):
        try:
            async with self.lock:
                if not self.cap:
                    await asyncio.to_thread(self.start)
                ret, frame = await asyncio.to_thread(self.cap.read)

            if not ret:
                print("Failed to read frame from camera.", flush=True)
                await self.stop()
                raise Exception("Camera read failed")

            pts = int(self.frame_count * self.pts_increment)
            time_base = Fraction(1, 90000) # 映像のtime_baseは通常90kHz

            frame_rgb = await asyncio.to_thread(cv2.cvtColor, frame, cv2.COLOR_BGR2RGB)

            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            video_frame.pts = pts
            video_frame.time_base = time_base

            self.frame_count += 1

            return video_frame

        except Exception:
            print("!!! AN ERROR OCCURRED IN VideoStreamTrack.recv !!!")
            raise

# --- WebRTC Audio Track ---
class AudioStreamTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self, samplerate=48000, channels=2):
        super().__init__()
        self.device = audio_input_device
        self.channels = channels
        self.samplerate = samplerate
        self.samples_per_frame = int(self.samplerate * 0.02)
        self.stream = None

        try:
            sd.check_input_settings(device=self.device, samplerate=self.samplerate)
            print(f"✅ Mic will run at the desired {self.samplerate} Hz.")
        except Exception as e:
            print(f"⚠️ Warning: {self.samplerate} Hz is not supported by the device ({e}).")
            device_info = sd.query_devices(self.device)
            self.samplerate = int(device_info['default_samplerate'])

        self._start_time = None
        self._timestamp = 0

        self.lock = asyncio.Lock()

    def start(self) -> bool:
        global audio_streaming_active
        audio_streaming_active = True
        print("Starting audio stream...", flush=True)
        try:
            self.stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, dtype='int16', device=self.device)
            self.stream.start()
            self._start_time = time.time()
            return True
        except Exception as e:
            print(f"Error starting audio stream: {e}", flush=True)
            self.stream = None
            return False

    def stop(self):
        asyncio.create_task(self._stop_async())
        super().stop()

    async def _stop_async(self):
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
                    if not self.start():
                        return None
                try:
                    data, _ = await asyncio.to_thread(self.stream.read, self.samples_per_frame)
                except sd.PortAudioError as e:
                    print(f"Error reading from audio stream: {e}", flush=True)
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
            print(f"Error creating audio frame: {e}", flush=True)

# --- WebSocket Signaling Handler ---
async def signaling_handler(websocket):
    global video_capture_device, audio_input_device
    active_websockets.add(websocket)

    pc = None
    relay = MediaRelay()
    server_video_track = None
    server_audio_track = None
    log_streaming_task = None

    async def start_webrtc():
        print("????????????start_webrtc called", flush=True)
        global audio_streaming_samplerate
        nonlocal pc, server_video_track, server_audio_track
        if server_video_track:
            server_video_track.stop()
            server_video_track = None
        if server_audio_track:
            await server_audio_track.stop()
            server_audio_track = None
            audio_streaming_samplerate = None
        if pc:
            await pc.close()
        pc = RTCPeerConnection()

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate is not None:
                await websocket.send(json.dumps({
                    "type": "ice",
                    "candidate": candidate.to_sdp(),
                    "sdpMid": candidate.sdp_mid,
                    "sdpMLineIndex": candidate.sdp_mline_index
                }))

        @pc.on("track")
        async def on_track(track):
            if track.kind == "audio":
                stream = None
                try:
                    while True:
                        frame = await track.recv()
                        if stream is None:
                            channels = len(frame.layout.channels)
                            samplerate = frame.sample_rate
                            print(f"🔊 Detected client audio format: {samplerate} Hz, {channels} channel(s)")
                            stream = sd.OutputStream(
                                device="USB",   # デバイス名に'USB'が含まれるものを自動で選択
                                samplerate=samplerate,
                                channels=channels,
                                dtype='int16'
                            )
                            print(f"{sd.query_devices(stream.device)["name"]}", flush=True)
                            stream.start()
                        raw_data = frame.to_ndarray()
                        reshaped_data = raw_data.reshape(-1, 2)
                        await asyncio.to_thread(stream.write, reshaped_data)

                except MediaStreamError:
                    print("Client audio stream ended.")
                finally:
                    stream.stop()
                    stream.close()

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc:
                print(f"RTC connection state: {pc.connectionState}", flush=True)


    async def stop_webrtc():
        print("stop_webrtc called", flush=True)
        nonlocal pc, server_video_track, server_audio_track
        if server_video_track:
            server_video_track.stop()
            server_video_track = None
        if server_audio_track:
            await server_audio_track.stop()
            server_audio_track = None
        if pc and pc.connectionState != "closed":
            await pc.close()
        pc = None
    
    async def stream_logs(websocket):
        await websocket.send("LOG:Starting log stream...")
        process = None
        try:
            command = "journalctl -f -n 50 -t startRPi.sh | grep -v 'websockets.server'"
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                await websocket.send("LOG:" + line.decode("utf-8").rstrip())
        except asyncio.CancelledError:
            print("Log streaming cancelled.", flush=True)
            process.terminate()
            await process.wait()
        except Exception as e:
            print(f"Error in log streaming: {e}", flush=True)
        finally:
            if process and process.returncode is None:
                process.terminate()
                await process.wait()

    async def update_connection():
        nonlocal pc
        for transceiver in pc.getTransceivers():
            kind = transceiver.kind
            sender = next((s for s in pc.getSenders() if s.track and s.track.kind == kind), None)
            direction = get_direction_from_sdp(pc.remoteDescription.sdp, kind)
            print(f"Transceiver kind: {kind}, direction: {direction}, sender present: {bool(sender)}", flush=True)

            if direction in ["recvonly", "sendrecv"]:
                if not sender:
                    if kind == "audio":
                        server_audio_track = AudioStreamTrack()
                        pc.addTrack(server_audio_track)
                        await websocket.send("AUM:STARTED")
                    elif kind == "video":
                        server_video_track = VideoStreamTrack()
                        pc.addTrack(server_video_track)
                        await websocket.send("VIM:STARTED")

            elif direction in ["sendonly", "inactive"]:
                if sender:
                    print(f"Stopping {kind} track as direction is {direction}", flush=True)
                    try:
                        if sender.track:
                            print(f"Stopping {kind} track...", flush=True)
                            sender.track.stop()
                        sender.replaceTrack(None)
                    except Exception as e:
                        print(f"Error stopping track: {e}", flush=True)
                    if kind == "audio":
                        print("Stopping server audio track...", flush=True)
                        server_audio_track = None
                        await websocket.send("AUM:STOPPED")
                    elif kind == "video":
                        server_video_track = None
                        await websocket.send("VIM:STOPPED")

            is_still_active = any(get_direction_from_sdp(pc.remoteDescription.sdp, t.kind) != "inactive" for t in pc.getTransceivers())

            if not is_still_active:
                await pc.close()
                pc = None

    def get_direction_from_sdp(sdp, kind="audio"):
        media_section = re.search(rf"m={kind}.*?(?=\r\nm=|\Z)", sdp, re.DOTALL)
        if not media_section:
            return "inactive"

        section_text = media_section.group(0)
        if "a=sendrecv" in section_text: return "sendrecv"
        if "a=sendonly" in section_text: return "sendonly"
        if "a=recvonly" in section_text: return "recvonly"
        if "a=inactive" in section_text: return "inactive"

        return "sendrecv"

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
                            audio_input_device = int(parts[2])
                        except Exception:
                            audio_input_device = None
                    else:
                        audio_input_device = None
                    await websocket.send("AUM:STARTING")
                elif message.startswith("AUDIO:ONSTOP"):
                    await websocket.send("AUM:STOPPING")
                elif message.startswith("VIDEO:ONSTART"):
                    parts = message.split(":")
                    if len(parts) >= 3:
                        try:
                            video_capture_device = int(parts[2])
                        except Exception:
                            video_capture_device = 0
                    else:
                        video_capture_device = 0
                    await websocket.send("VIM:STARTING")
                elif message.startswith("VIDEO:ONSTOP"):
                    await websocket.send("VIM:STOPPING")
                elif message.startswith("CLIENT_AUDIO:ONSTART"):
                    await websocket.send("ACM:STARTED")
                elif message.startswith("CLIENT_AUDIO:ONSTOP"):
                    await stop_webrtc()
                    await websocket.send("ACM:STOPPED")
                elif message.startswith("LOGS:ONSTART"):
                    if log_streaming_task:
                        log_streaming_task.cancel()
                        log_streaming_task = None
                    log_streaming_task = asyncio.create_task(stream_logs(websocket))
                    await websocket.send("LOGS:STARTED")
                elif message.startswith("LOGS:ONSTOP"):
                    if log_streaming_task:
                        log_streaming_task.cancel()
                        log_streaming_task = None
                    await websocket.send("LOGS:STOPPED")
                elif message.startswith("KEY:"):
                    try:
                        key_event = json.loads(message[4:])
                        send_key_event(key_event)
                    except Exception as e:
                        await websocket.send(f"ERR:KEY:{e}")
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
                        await websocket.send(f"ERR:MOUSE:{e}")
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
                elif message == "RESTART:NOW":
                    await shutdown()
                    sys.exit(10)
                # --- WebRTCシグナリング ---
                else:
                    try:
                        msg = json.loads(message)
                        if msg["type"] == "offer":
                            if not pc:
                                await start_webrtc()
                            offer = RTCSessionDescription(sdp=msg["sdp"], type=msg["type"])
                            await pc.setRemoteDescription(offer)
                            await update_connection()
                            if not pc:
                                continue
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
                        import traceback
                        traceback.print_exc()
            else:
                print(f"Received unexpected binary data: {len(message)} bytes", flush=True)
    finally:
        await stop_webrtc()
        active_websockets.discard(websocket)
        if log_streaming_task:
            log_streaming_task.cancel()
            log_streaming_task = None

async def shutdown():
    global main_task
    print("Shutting down, closing websockets...", flush=True)
    await asyncio.gather(*(ws.close() for ws in list(active_websockets)), return_exceptions=True)
    for task in asyncio.all_tasks():
        if not task.done():
            task.cancel()
    if main_task:
        main_task.cancel()

async def send_to_discord():
    load_dotenv()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 実際に接続はせず、OSがどのIPを使うかを判断させる
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = "127.0.0.1" # 取得失敗時のフォールバック
    finally:
        s.close()
    async with aiohttp.ClientSession() as session:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        payload = {"content": "✅ WebRTC: IP Address: " + ip_address + ":8765"}
        try:
            async with session.post(webhook_url, json=payload) as resp:
                if 200 <= resp.status < 300:
                    print("Message sent to Discord successfully.", flush=True)
                else:
                    print(f"Failed to send message to Discord: {resp.status}", flush=True)
        except Exception as e:
            print(f"Error sending message to Discord: {e}", flush=True)

# --- WebSocket Server ---
async def main():
    global main_task
    await send_to_discord()
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    async with websockets.serve(signaling_handler, "0.0.0.0", 8765):
        main_task = asyncio.current_task()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            print("Main task cancelled. Server is stopping.")

if __name__ == "__main__":
    asyncio.run(main())