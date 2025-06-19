#!/usr/bin/env python3
import asyncio
import websockets
import threading
import sys
import termios
import tty
import json
import subprocess
import cv2
import numpy as np
import struct
import time
import signal

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# USB HID キーボードのスキャンコードマッピング（日本語キーボード対応）
KEY_MAP = {
    # アルファベット
    'a': 4, 'b': 5, 'c': 6, 'd': 7, 'e': 8, 'f': 9, 'g': 10, 'h': 11, 'i': 12, 'j': 13,
    'k': 14, 'l': 15, 'm': 16, 'n': 17, 'o': 18, 'p': 19, 'q': 20, 'r': 21, 's': 22,
    't': 23, 'u': 24, 'v': 25, 'w': 26, 'x': 27, 'y': 28, 'z': 29,

    # 数字
    '1': 30, '2': 31, '3': 32, '4': 33, '5': 34, '6': 35, '7': 36, '8': 37, '9': 38, '0': 39,

    # 記号
    '-': 45, '^': 46, '@': 47, '[': 48, ']': 49, '\\': 50, ';': 51, ':': 52, ',': 54, '.': 55, '/': 56,
    '`': 53, '=': 46,  # 日本語キーボードの「=」は「^」と同じスキャンコード

    # スペースと制御キー
    ' ': 44, '\n': 40, 'Enter': 40,'Return': 40, 'Backspace': 42,  # スペース、エンター、バックスペース
    'Tab': 43, 'Escape': 41,

    # 機能キー
    'CapsLock': 57, 'F1': 58, 'F2': 59, 'F3': 60, 'F4': 61, 'F5': 62, 'F6': 63,
    'F7': 64, 'F8': 65, 'F9': 66, 'F10': 67, 'F11': 68, 'F12': 69,

    # 特殊キー
    'PrintScreen': 70, 'ScrollLock': 71, 'Pause': 72, 'Insert': 73, 'Home': 74, 'PageUp': 75,
    'Delete': 76, 'End': 77, 'PageDown': 78, 'RightArrow': 79, 'ArrowRight': 79, 'LeftArrow': 80, 'ArrowLeft': 80,
    'DownArrow': 81,'ArrowDown': 81, 'UpArrow': 82, 'ArrowUp': 82,

    # テンキー
    'NumLock': 83, 'Keypad/': 84, 'Keypad*': 85, 'Keypad-': 86, 'Keypad+': 87, 'KeypadEnter': 88,
    'Keypad1': 89, 'Keypad2': 90, 'Keypad3': 91, 'Keypad4': 92, 'Keypad5': 93, 'Keypad6': 94,
    'Keypad7': 95, 'Keypad8': 96, 'Keypad9': 97, 'Keypad0': 98, 'Keypad.': 99,

    # 日本語特有のキー
    'NonUS#': 100, 'NonUS\\': 100,  # 日本語キーボードの「\」
    'Application': 101, 'Power': 102,
    'Zenkaku': 135,  # 半角/全角
    'Backquote': 135,
    'International2': 136,  # カタカナ/ひらがな
    'International3': 137,  # 無変換
    'NonConvert': 137,
    'International4': 138,  # 変換
    'Convert': 138,
    'International5': 139,  # ひらがな
    'LANG1': 144,  # 日本語キーボードの「かな」
    'Hiragana': 144,
    'KanaMode': 144,
    'LANG2': 145,  # 日本語キーボードの「英数」
}

SHIFT_REQUIRED = {
    'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f', 'G': 'g', 'H': 'h',
    'I': 'i', 'J': 'j', 'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n', 'O': 'o', 'P': 'p',
    'Q': 'q', 'R': 'r', 'S': 's', 'T': 't', 'U': 'u', 'V': 'v', 'W': 'w', 'X': 'x',
    'Y': 'y', 'Z': 'z', '!': '1', '"': '2', '#': '3', '$': '4', '%': '5', '&': '6',
    "'": '7', '(': '8', ')': '9', '=': '0', '~': '^', '|': '\\', '`': '@', '{': '[',
    '}': ']', '+': ';', '*': ':', '<': ',', '>': '.', '?': '/', '_': '\\'
}

MODIFIER_MAP = {
    'ctrl': 0x01,  # 左 Ctrl
    'shift': 0x02,  # 左 Shift
    'alt': 0x04,  # 左 Alt
    'gui': 0x08,  # 左 GUI（Windowsキー）
    'ctrl_r': 0x10,  # 右 Ctrl
    'shift_r': 0x20,  # 右 Shift
    'alt_r': 0x40,  # 右 Alt
    'gui_r': 0x80   # 右 GUI（Windowsキー）
}

NULL_CHAR = chr(0)

rtsp_server_running = False
rtsp_server_loop = None
rtsp_server_process = None # GStreamerをサブプロセスで動かす場合
video_capture_device = "/dev/video0"
rtsp_port = "5554"
rtsp_mount_point = "/stream"

def write_report(report):
    try:
        with open('/dev/hidg0', 'rb+') as fd: fd.write(report.encode())
    except Exception as e: print(f"Error /dev/hidg0: {e}", flush=True)

def write_mouse(report):
    try:
        with open('/dev/hidg1', 'rb+') as fd: fd.write(report)
    except Exception as e: print(f"Error /dev/hidg1: {e}", flush=True)

def send_key_event(key_event):
    modifiers = 0
    if key_event.get('ctrl'):  modifiers |= MODIFIER_MAP['ctrl']    # TODO:後でまとめる
    if key_event.get('shift'): modifiers |= MODIFIER_MAP['shift']
    if key_event.get('alt'):   modifiers |= MODIFIER_MAP['alt']
    if key_event.get('meta'):  modifiers |= MODIFIER_MAP['gui']
    key = key_event.get('key')
    keycode = None

    # Shift
    if key in SHIFT_REQUIRED:
        modifiers |= MODIFIER_MAP['shift']
        base_char = SHIFT_REQUIRED[key]
        keycode = KEY_MAP.get(base_char)
    else:
        keycode = KEY_MAP.get(key) or KEY_MAP.get(key_event.get('code'))  # codeも参照

    if not keycode and (modifiers != 0):
        # キーコード0で修飾キーのみ押下
        report = chr(modifiers) + NULL_CHAR*7
        write_report(report)
        write_report(NULL_CHAR*8)  # キーリリース
    elif keycode:
        report = chr(modifiers) + NULL_CHAR + chr(keycode) + NULL_CHAR*5
        write_report(report)
        write_report(NULL_CHAR*8)  # キーリリース
    else:
        print(f"Unsupported key: {key_event}")

def move_mouse(x_ratio, y_ratio, left=0, right=0, center=0, side1=0, side2=0, wheel=0, hwheel=0):
    """
    タブレット型絶対座標マウスHIDレポート送信
    :param x_ratio: 0.0〜1.0 のX座標
    :param y_ratio: 0.0〜1.0 のY座標
    :param left: 1=左ボタン, 0=離す
    :param right: 1=右ボタン, 0=離す
    :param center: 1=中ボタン, 0=離す
    :param side1: サイドボタン1（例: 戻る）
    :param side2: サイドボタン2（例: 進む）
    :param wheel: 垂直ホイール（-127〜127）
    :param hwheel: 水平ホイール（-127〜127）
    """
    abs_x = int(x_ratio * 32767)
    abs_y = int(y_ratio * 32767)
    wheel_val = max(-128, min(127, int(wheel)))
    hwheel_val = max(-128, min(127, int(hwheel)))
    # ボタンビット: left=左, right=右, center=中
    buttons = (
        (left & 1) |
        ((right & 1) << 1) |
        ((center & 1) << 2) |
        ((side1 & 1) << 3) |
        ((side2 & 1) << 4)
    )
    report = bytes([
        buttons,
        abs_x & 0xFF, (abs_x >> 8) & 0xFF,
        abs_y & 0xFF, (abs_y >> 8) & 0xFF,
        wheel_val & 0xFF,
        hwheel_val & 0xFF
    ])
    write_mouse(report)

class RTSPServer():
    def __init__(self):
        self.server = GstRtspServer.Server()
        self.server.set_service(rtsp_port)
        self.mounts = self.server.get_mount_points()
        
        # Raspberry Pi 5では、v4l2src -> videoconvert -> v4l2h264enc (ハードウェアエンコーダ) を使う
        # `!` の前後にスペースを入れること
        # 解像度やフレームレートはキャプチャーボードとエンコーダの能力に合わせて調整
        # `queue` エレメントを適宜挟むと安定性が向上することがある
        launch_str = (
            f"( v4l2src device={video_capture_device} ! "
            f"videoconvert ! queue ! "
            f"video/x-raw,width=1280,height=720,framerate=30/1 ! queue ! " # 必要に応じて解像度・FPS指定
            f"v4l2h264enc extra-controls=\"controls,video_bitrate=2000000\" ! " # ビットレート2Mbps例
            f"rtph264pay name=pay0 pt=96 )" # H.235ならrtph265pay
        )
        print(f"GStreamer launch string: {launch_str}", flush=True)

        self.factory = GstRtspServer.RTSPMediaFactory()
        self.factory.set_launch_string(launch_str)
        self.factory.set_shared(True) # 複数のクライアントが同じストリームを視聴可能にする
        self.mounts.add_factory(rtsp_mount_point, self.factory)
        
        self.main_loop = GLib.MainLoop()

    def start(self):
        global rtsp_server_running, rtsp_server_loop
        if rtsp_server_running:
            print("RTSP server is already running.", flush=True)
            return
        
        print("Starting RTSP server...", flush=True)
        self.server.attach(None) # GLib.MainContext (Noneでデフォルト)
        rtsp_server_running = True
        rtsp_server_loop = self.main_loop # グローバルにループを保持

        # GLib.MainLoopを別スレッドで実行
        self.loop_thread = threading.Thread(target=self.main_loop.run, daemon=True)
        self.loop_thread.start()
        print(f"RTSP Server started. Stream available at rtsp://<RaspberryPi_IP>:{rtsp_port}{rtsp_mount_point}", flush=True)

    def stop(self):
        global rtsp_server_running, rtsp_server_loop
        if not rtsp_server_running or not rtsp_server_loop:
            print("RTSP server is not running.", flush=True)
            return
        
        print("Stopping RTSP server...", flush=True)
        rtsp_server_loop.quit()
        self.loop_thread.join(timeout=2) # スレッド終了を待つ
        # GstRtspServer.Serverオブジェクトの明示的なクリーンアップは通常不要
        # self.mounts.remove_factory(rtsp_mount_point) # 必要なら
        rtsp_server_running = False
        rtsp_server_loop = None
        print("RTSP server stopped.", flush=True)

rtsp_instance = None

def handler(conn):
    buffer = ""
    while True:
        data = conn.recv(1024)
        if not data:
            break
        buffer += data.decode()
        while '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            cmd = line.strip()
            if cmd.startswith("KEY:"):
                key_event = json.loads(cmd[4:]) # key:を除いてパース
                send_key_event(key_event)
            elif cmd.startswith("MOUSE:"):
                try:
                    _, params = cmd.split(':', 1)
                    x_str, y_str, left, right, center, side1, side2, wheel, hwheel = params.split(',')
                    move_mouse(
                        float(x_str), float(y_str),
                        int(left), int(right), int(center), int(side1), int(side2), int(wheel), int(hwheel)
                    )
                except Exception as e:
                    print(f"MOUSE parse error: {e}", flush=True)
            elif cmd == "CMD:ISTICKTOIT_USB":
                try:
                    subprocess.run(['sudo', '/bin/isticktoit_usb'], check=True)
                    conn.sendall(b'OK\n')
                except Exception as e:
                    conn.sendall(f'ERR:{e}\n'.encode())
            elif cmd == "CMD:REMOVE_GADGET":
                try:
                    subprocess.run(['sudo', 'sh', '-c', 'echo "" > /sys/kernel/config/usb_gadget/isticktoit/UDC'], check=True)
                    subprocess.run(['sudo', 'rm', '-rf', '/sys/kernel/config/usb_gadget/isticktoit'], check=True)
                    conn.sendall(b'OK\n')
                except Exception as e:
                    conn.sendall(f'ERR:{e}\n'.encode())
    conn.close()

# WebSocketハンドラ
async def handler(websocket, path):
    global video_streaming_active, rtsp_instance # video_streaming_active は RTSPサーバーの状態と連動させる
    print(f"Client connected from {websocket.remote_address}", flush=True)

    try:
        async for message in websocket:
            if isinstance(message, str):
                cmd = message.strip()
                if cmd.startswith("KEY:"):
                    try:
                        key_event = json.loads(cmd[4:])
                        send_key_event(key_event)
                    except Exception as e: print(f"Error KEY: {e}", flush=True)

                elif cmd.startswith("MOUSE:"):
                    try:
                        _, params = cmd.split(':', 1)
                        values = list(map(float, params.split(',')))
                        move_mouse(values[0], values[1], int(values[2]), int(values[3]), int(values[4]), int(values[5]), int(values[6]), int(values[7]), int(values[8]))
                    except Exception as e: print(f"Error MOUSE: {e}", flush=True)

                elif cmd == "VIDEO:ONSTART":
                    if not rtsp_server_running:
                        print("VIDEO:ONSTART received. Starting RTSP server.", flush=True)
                        if rtsp_instance is None:
                             rtsp_instance = RTSPServer()
                        rtsp_instance.start() # 別スレッドでGLib.MainLoopが実行される
                        if rtsp_server_running:
                             await websocket.send(f"VIDEO:STARTED_RTSP:{rtsp_port}{rtsp_mount_point}")
                        else:
                             await websocket.send("VIDEO:ERROR_STARTING_RTSP")
                    else:
                        print("RTSP server already active.", flush=True)
                        await websocket.send(f"VIDEO:ALREADY_ACTIVE_RTSP:{rtsp_port}{rtsp_mount_point}")

                elif cmd == "VIDEO:ONSTOP":
                    if rtsp_server_running and rtsp_instance:
                        print("VIDEO:ONSTOP received. Stopping RTSP server.", flush=True)
                        rtsp_instance.stop()
                        await websocket.send("VIDEO:STOPPED_RTSP")
                    else:
                        print("RTSP server not active or instance not created.", flush=True)
                        await websocket.send("VIDEO:NOT_ACTIVE_RTSP")
                
                elif cmd == "CMD:ISTICKTOIT_USB":
                    try:
                        subprocess.run(['sudo', '/usr/bin/isticktoit_usb'], check=True, timeout=15)
                        await websocket.send('CMD_RESP:OK_ISTICKTOIT_USB')
                    except Exception as e: await websocket.send(f'CMD_RESP:ERR_ISTICKTOIT_USB:{e}')

                elif cmd == "CMD:REMOVE_GADGET":
                    try:
                        udc_path = '/sys/kernel/config/usb_gadget/isticktoit/UDC'
                        if subprocess.run(['sudo', 'test', '-f', udc_path]).returncode == 0:
                             subprocess.run(['sudo', 'sh', '-c', f'echo "" > {udc_path}'], check=True, timeout=5)
                        await websocket.send('CMD_RESP:OK_REMOVE_GADGET')
                    except Exception as e: await websocket.send(f'CMD_RESP:ERR_REMOVE_GADGET:{e}')
                else:
                    print(f"Unknown string command: {cmd}", flush=True)
            # バイナリデータの受信は想定しない
    except websockets.exceptions.ConnectionClosed:
        print(f"Client {websocket.remote_address} disconnected.", flush=True)
    except Exception as e:
        print(f"Error in WebSocket handler: {e}", flush=True)
    finally:
        if rtsp_server_running and rtsp_instance:
            print("Client disconnected, stopping RTSP server.", flush=True)
            rtsp_instance.stop()
        print(f"Client {websocket.remote_address} connection closed.", flush=True)


async def main_async():
    Gst.init(None) # GStreamerの初期化

    # USBガジェット設定の試み (前回と同様)
    try:
        print("Attempting to configure USB gadget...", flush=True)
        subprocess.run(['sudo', '/usr/local/bin/isticktoit_usb'], check=True, timeout=15)
        print("USB gadget configured.", flush=True)
    except Exception as e:
        print(f"Failed to configure USB gadget: {e}", flush=True)

    # WebSocketサーバー起動
    websocket_server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("WebSocket server started on ws://0.0.0.0:8765", flush=True)
    
    # シグナルハンドラの設定 (Ctrl+Cで終了できるように)
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    await stop # Ctrl+C または SIGTERM を待つ

    # サーバー停止処理
    print("Shutting down servers...", flush=True)
    if rtsp_server_running and rtsp_instance:
        rtsp_instance.stop()
    websocket_server.close()
    await websocket_server.wait_closed()
    print("Servers stopped.", flush=True)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nShutting down server by KeyboardInterrupt...")
    except Exception as e:
        print(f"Unhandled exception in main: {e}", flush=True)
    finally:
        print("Server stopped.")

if __name__ == "__main__":
    main()