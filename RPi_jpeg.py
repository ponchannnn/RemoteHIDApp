#!/usr/bin/env python3
# pip install opencv-python-headless numpy websockets
# sudo apt update
# sudo apt install python3-gi python3-gst-1.0 gir1.2-gst-rtsp-server-1.0 gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-omx-rpi # RPi4以前のOMX、RPi5ではv4l2m2mが主
# sudo apt install libgstreamer1.0-dev libgstrtspserver-1.0-dev # 開発用ヘッダ等
# sudo apt install gstreamer1.0-v4l2 # Video4Linux2プラグイン
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

# グローバル変数（映像送出制御用）
video_streaming_active = False
video_capture_device = 0 # キャプチャーデバイス番号 (例: /dev/video0)
jpeg_quality = 70 # JPEG品質 (0-100)
target_fps = 60 # 目標フレームレート

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

# 映像送出ループ
async def video_stream_loop(websocket):
    global video_streaming_active
    print("Video stream loop started.", flush=True)
    cap = None
    try:
        cap = cv2.VideoCapture(video_capture_device)
        if not cap.isOpened():
            print(f"Cannot open camera device {video_capture_device}", flush=True)
            await websocket.send("ERROR:Cannot open camera")
            video_streaming_active = False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, target_fps)
        print(f"Actual FPS: {cap.get(cv2.CAP_PROP_FPS)}", flush=True)

        frame_interval = 1.0 / target_fps
        last_frame_time = time.monotonic()

        while video_streaming_active:
            current_time = time.monotonic()
            if (current_time - last_frame_time) < frame_interval:
                await asyncio.sleep(frame_interval - (current_time - last_frame_time)) # 少し待機してFPSを制御
            last_frame_time = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                print("Can't receive frame. Stopping video stream.", flush=True)
                await websocket.send("ERROR:Failed to receive frame")
                break

            # フレームをJPEGにエンコード
            result, encoded_frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if not result:
                print("JPEG encode error", flush=True)
                continue

            try:
                # バイナリデータとして送信
                await websocket.send(encoded_frame.tobytes())
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket connection closed by client during video stream.", flush=True)
                break
            except Exception as e:
                print(f"Error sending video frame: {e}", flush=True)
                break
        
    except Exception as e:
        print(f"Error in video_stream_loop: {e}", flush=True)
        if websocket.open:
            await websocket.send(f"ERROR:Video stream failure - {e}")
    finally:
        if cap and cap.isOpened():
            cap.release()
        video_streaming_active = False # ループ終了時にフラグを確実に倒す
        print("Video stream loop finished.", flush=True)


# WebSocketハンドラ
async def handler(websocket):
    global video_streaming_active
    print(f"Client connected from {websocket.remote_address}", flush=True)
    video_task = None

    try:
        async for message in websocket:
            # print(f"Received message: {message[:100]}", flush=True) # 長いメッセージは一部表示
            if isinstance(message, str):
                cmd = message.strip()
                if cmd.startswith("KEY:"):
                    try:
                        key_event = json.loads(cmd[4:])
                        send_key_event(key_event)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON for KEY event: {cmd[4:]}", flush=True)
                    except Exception as e:
                        print(f"Error processing KEY event: {e}", flush=True)

                elif cmd.startswith("MOUSE:"):
                    try:
                        _, params = cmd.split(':', 1)
                        # x,y,left,right,center,side1,side2,wheel,hwheel
                        values = list(map(float, params.split(','))) # floatに統一して後でintに
                        move_mouse(
                            values[0], values[1], # x_ratio, y_ratio
                            int(values[2]), int(values[3]), int(values[4]), # left, right, center
                            int(values[5]), int(values[6]), # side1, side2
                            int(values[7]), int(values[8])  # wheel, hwheel
                        )
                    except ValueError:
                         print(f"Invalid MOUSE parameters. Expected 9 floats. Got: {params}", flush=True)
                    except Exception as e:
                        print(f"Error processing MOUSE event: {e}", flush=True)

                elif cmd == "VIDEO:ONSTART":
                    if not video_streaming_active:
                        video_streaming_active = True
                        print("VIDEO:ONSTART received. Starting video stream task.", flush=True)
                        # asyncio.create_task() を使ってバックグラウンドで実行
                        video_task = asyncio.create_task(video_stream_loop(websocket))
                        await websocket.send("VIDEO:STARTED")
                    else:
                        print("Video stream already active.", flush=True)
                        await websocket.send("VIDEO:ALREADY_ACTIVE")

                elif cmd == "VIDEO:ONSTOP":
                    if video_streaming_active:
                        video_streaming_active = False
                        print("VIDEO:ONSTOP received. Attempting to stop video stream.", flush=True)
                        if video_task:
                            # video_task.cancel() # タスクをキャンセル
                            try:
                                await asyncio.wait_for(video_task, timeout=1.0) # 終了を待つ（タイムアウト付き）
                            except asyncio.TimeoutError:
                                print("Video stream task did not finish in time.", flush=True)
                            except asyncio.CancelledError:
                                print("Video stream task cancelled.", flush=True)
                        await websocket.send("VIDEO:STOPPED")
                    else:
                        print("Video stream not active.", flush=True)
                        await websocket.send("VIDEO:NOT_ACTIVE")
                
                elif cmd == "CMD:ISTICKTOIT_USB":
                    try:
                        subprocess.run(['sudo', '/usr/local/bin/isticktoit_usb'], check=True, timeout=15)
                        await websocket.send('CMD_RESP:OK_ISTICKTOIT_USB')
                    except subprocess.CalledProcessError as e:
                        await websocket.send(f'CMD_RESP:ERR_ISTICKTOIT_USB_CALLED_PROCESS_ERROR:{e.stderr.decode() if e.stderr else e}')
                    except subprocess.TimeoutExpired:
                        await websocket.send('CMD_RESP:ERR_ISTICKTOIT_USB_TIMEOUT')
                    except FileNotFoundError:
                        await websocket.send('CMD_RESP:ERR_ISTICKTOIT_USB_NOT_FOUND')
                    except Exception as e:
                        await websocket.send(f'CMD_RESP:ERR_ISTICKTOIT_USB:{e}')
                
                elif cmd == "CMD:REMOVE_GADGET": # より安全なガジェット削除/無効化を検討
                    try:
                        # まずUDCからアンバインド
                        udc_path = '/sys/kernel/config/usb_gadget/isticktoit/UDC'
                        # isticktoitディレクトリが存在するか確認
                        if subprocess.run(['sudo', 'test', '-f', udc_path]).returncode == 0:
                             subprocess.run(['sudo', 'sh', '-c', f'echo "" > {udc_path}'], check=True, timeout=5)
                        # その後、設定ディレクトリを削除（オプション、アンバインドだけで十分な場合も）
                        # subprocess.run(['sudo', 'rm', '-rf', '/sys/kernel/config/usb_gadget/isticktoit'], check=True, timeout=5)
                        await websocket.send('CMD_RESP:OK_REMOVE_GADGET')
                    except Exception as e:
                        await websocket.send(f'CMD_RESP:ERR_REMOVE_GADGET:{e}')
                else:
                    print(f"Unknown string command: {cmd}", flush=True)
            elif isinstance(message, bytes):
                # 現状、クライアントからバイナリデータは想定していない
                print(f"Received unexpected binary data: {len(message)} bytes", flush=True)

    except websockets.exceptions.ConnectionClosedOK:
        print(f"Client {websocket.remote_address} disconnected normally.", flush=True)
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Client {websocket.remote_address} disconnected with error: {e}", flush=True)
    except Exception as e:
        print(f"Error in WebSocket handler: {e}", flush=True)
    finally:
        video_streaming_active = False # 念のため接続終了時にも停止
        if video_task and not video_task.done():
            video_task.cancel()
            print("Video task cancelled on disconnect.", flush=True)
        print(f"Client {websocket.remote_address} connection closed.", flush=True)


async def main_async():
    # USBガジェット設定の試み
    try:
        print("Attempting to configure USB gadget...", flush=True)
        # isticktoit_usb スクリプトのフルパスを指定
        subprocess.run(['sudo', '/usr/bin/isticktoit_usb'], check=True, timeout=15)
        print("USB gadget configured.", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure USB gadget (CalledProcessError): {e.cmd} returned {e.returncode}", flush=True)
        if e.stderr: print(f"Stderr: {e.stderr.decode()}", flush=True)
    except subprocess.TimeoutExpired:
        print("Timeout configuring USB gadget.", flush=True)
    except FileNotFoundError:
        print("ERROR: isticktoit_usb script not found. Please check the path /usr/local/bin/isticktoit_usb.", flush=True)
    except Exception as e:
        print(f"An unexpected error occurred during USB gadget configuration: {e}", flush=True)

    # WebSocketサーバー起動
    # IPv4 と IPv6 の両方でリッスンする場合:
    # await websockets.serve(handler, "::", 8765) # "::" はIPv6のワイルドカードアドレス
    # IPv4 のみでリッスンする場合:
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("WebSocket server started on ws://0.0.0.0:8765", flush=True)
        await asyncio.Future()  # サーバーを永続的に実行

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