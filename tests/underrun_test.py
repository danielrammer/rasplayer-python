#!/usr/bin/env python3
"""underrun_test.py
Simple test that plays a WAV file in a loop using pygame mixer and optionally tails journalctl
to detect ALSA underrun log messages.

Usage:
    python tests/underrun_test.py /path/to/sample.wav --buffer 4096 --duration 30

This is intended to be run on the Raspberry Pi where the underruns were observed.
"""
import argparse
import subprocess
import sys
import time
import threading

import pygame


def tail_journalctl_pattern(pattern, stop_event):
    proc = subprocess.Popen(["journalctl", "-f"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        while not stop_event.is_set():
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            if pattern in line:
                print("[journalctl] ", line.strip())
    finally:
        proc.terminate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='WAV file to play in loop')
    parser.add_argument('--buffer', type=int, default=4096, help='mixer buffer size')
    parser.add_argument('--duration', type=int, default=30, help='test duration in seconds')
    parser.add_argument('--check-journal', action='store_true', help='tail journalctl for "underrun" messages')
    args = parser.parse_args()

    # init mixer
    pygame.mixer.pre_init(44100, -16, 2, buffer=args.buffer)
    pygame.mixer.init()

    sound = pygame.mixer.Sound(args.file)

    stop_event = threading.Event()
    if args.check_journal:
        t = threading.Thread(target=tail_journalctl_pattern, args=("underrun", stop_event), daemon=True)
        t.start()

    print(f"Playing {args.file} in loop for {args.duration}s with buffer={args.buffer}")
    end_time = time.time() + args.duration
    try:
        while time.time() < end_time:
            sound.play()
            # sleep a bit less than sound length or a small interval
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        pygame.mixer.quit()
        print("Test finished")
