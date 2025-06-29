#!/usr/bin/env python3
import socket
import threading
import sys
import termios
import tty
import json
import subprocess

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

def write_report(report):
    with open('/dev/hidg0', 'rb+') as fd:
        fd.write(report.encode())

def write_mouse(report):
    with open('/dev/hidg1', 'rb+') as fd:
        fd.write(report)

def get_key():
    """キーボード入力を取得（特殊キー対応）"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ord(ch) == 127:  # バックスペース
            return 'Backspace'
        elif ord(ch) == 27:  # エスケープシーケンス
            next1, next2 = sys.stdin.read(1), sys.stdin.read(1)
            if next1 == '[':
                if next2 == '1':  # Home
                    sys.stdin.read(1)  # Consume '~'
                    return 'Home'
                elif next2 == '2':  # Insert
                    sys.stdin.read(1)  # Consume '~'
                    return 'Insert'
                elif next2 == '3':  # Delete
                    sys.stdin.read(1)  # Consume '~'
                    return 'Delete'
                elif next2 == '4':  # End
                    sys.stdin.read(1)  # Consume '~'
                    return 'End'
                elif next2 == '5':  # PageUp
                    sys.stdin.read(1)  # Consume '~'
                    return 'PageUp'
                elif next2 == '6':  # PageDown
                    sys.stdin.read(1)  # Consume '~'
                    return 'PageDown'
                elif next2 == 'A':  # Up Arrow
                    return 'UpArrow'
                elif next2 == 'B':  # Down Arrow
                    return 'DownArrow'
                elif next2 == 'C':  # Right Arrow
                    return 'RightArrow'
                elif next2 == 'D':  # Left Arrow
                    return 'LeftArrow'
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

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

def handle_client(conn):
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

def main():
    try:
        print("Attempting to configure USB gadget...", flush=True)
        subprocess.run(['sudo', '/usr/local/bin/isticktoit_usb'], check=True, timeout=10) # 環境に合わせてパスを修正
        print("USB gadget configured.", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure USB gadget: {e}", flush=True)
    except subprocess.TimeoutExpired:
        print("Timeout configuring USB gadget.", flush=True)
    except FileNotFoundError:
        print("ERROR: isticktoit_usb script not found. Please check the path.", flush=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 5555))  # ポートは任意
    server.listen(1)
    print("Waiting for connection...")
    try:
        while True:
            conn, addr = server.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn,))
            client_thread.daemon = True # メインスレッド終了時に子スレッドも終了
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.close()

if __name__ == "__main__":
    main()