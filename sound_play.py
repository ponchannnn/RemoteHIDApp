#!/usr/bin/env python3

import sounddevice as sd
import scipy.io.wavfile
import numpy as np
import os

FILENAME = 'test.wav'
TARGET_DEVICE = 'USB'

def play_wav_with_outputstream_test():
    print("--- Sounddevice OutputStream Test ---")

    if not os.path.exists(FILENAME):
        return

    stream = None
    try:
        samplerate, data = scipy.io.wavfile.read(FILENAME)
        
        channels = data.shape[1] if data.ndim > 1 else 1
        dtype = data.dtype
        print(f"info:{samplerate} Hz, {channels} ch, {dtype}")

        print(f"Opening '{TARGET_DEVICE}' ")
        stream = sd.OutputStream(
            device=TARGET_DEVICE,
            samplerate=samplerate,
            channels=channels,
            dtype=dtype
        )
        
        selected_device_index = stream.device
        device_info = sd.query_devices(selected_device_index)
        selected_device_name = device_info['name']
        print(f"Opened device with '{selected_device_name}' (Index: {selected_device_index}) ")
        
        stream.start()
        print("playing...")
        stream.write(data)
        print("Playback finished.")

    except Exception as e:
        print(f"!!! Error occurred: {e}")
        if 'Invalid device' in str(e):
            print("\n--- Available output devices ---")
            print(sd.query_devices())
            print("---------------------------------")
            print(f"Could not find or unsupported output device named '{TARGET_DEVICE}'.")

    finally:
        if stream:
            stream.stop()
            stream.close()
            print("Stream closed.")

if __name__ == '__main__':
    play_wav_with_outputstream_test()