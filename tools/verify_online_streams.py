#!/usr/bin/env python3
"""Bounded manual VLC check for the OnlinePlayer station table."""

import argparse
import ast
from pathlib import Path
import subprocess
import time

import vlc


def load_stations(source_path):
    tree = ast.parse(Path(source_path).read_text(), filename=str(source_path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "OnlinePlayer":
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(isinstance(target, ast.Name) and target.id == "stations"
                       for target in statement.targets):
                    return ast.literal_eval(statement.value)
    raise RuntimeError("OnlinePlayer.stations was not found")


def wait_for_stream(player, timeout):
    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        state = player.get_state()
        last_state = state
        if state == vlc.State.Playing:
            return True, state
        if state in (vlc.State.Error, vlc.State.Ended, vlc.State.Stopped):
            return False, state
        time.sleep(0.10)
    return False, last_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="path to OnlinePlayer.py")
    parser.add_argument("--start", type=int, default=1,
                        help="first one-based station number")
    parser.add_argument("--end", type=int, default=15,
                        help="last one-based station number")
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    stations = load_stations(args.source)
    try:
        instance = vlc.Instance("--aout=dummy", "--no-video",
                                "--network-caching=1000", "--http-reconnect")
    except (NameError, OSError) as exc:
        instance = None
        print("STREAM_VERIFY using_cli reason=%r" % (exc,), flush=True)
    failures = 0
    for number in range(args.start, min(args.end, len(stations)) + 1):
        name, url = stations[number - 1]
        started = time.monotonic()
        if instance is None:
            command = [
                "vlc", "-I", "dummy", "--aout=dummy", "--no-video",
                "--network-caching=1000", "--http-reconnect",
                "--run-time=3", "--play-and-exit", "-vv", url]
            try:
                completed = subprocess.run(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=args.timeout)
                log = completed.stdout
                passed = ('using audio decoder module "mpg123"' in log and
                          "Your input can't be opened" not in log)
                state = "decoded" if passed else "open_failed"
                result = completed.returncode
                if not passed:
                    print(log[-2000:], flush=True)
            except subprocess.TimeoutExpired as exc:
                log = exc.stdout or ""
                if isinstance(log, bytes):
                    log = log.decode(errors="replace")
                passed = ('using audio decoder module "mpg123"' in log and
                          "Your input can't be opened" not in log)
                state = "decoded_timeout" if passed else "timeout"
                result = None
                if not passed:
                    print(log[-2000:], flush=True)
        else:
            player = instance.media_player_new()
            media = instance.media_new(url)
            media.add_option(":network-caching=1000")
            media.add_option(":http-reconnect")
            player.set_media(media)
            result = player.play()
            passed, state = wait_for_stream(player, args.timeout)
        elapsed = time.monotonic() - started
        print("STREAM_VERIFY station=%d result=%s play_return=%s state=%s "
              "elapsed=%.3f name=%r url=%s" %
              (number, "PASS" if passed else "FAIL", result, state,
               elapsed, name, url), flush=True)
        failures += 0 if passed else 1
        if instance is not None:
            player.stop()
            player.release()
    if instance is not None:
        instance.release()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
