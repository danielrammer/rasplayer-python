"""Minimal systemd watchdog notification client (no external dependency)."""
import os
import socket
import time


class WatchdogNotifier:
    def __init__(self):
        self.address = os.environ.get("NOTIFY_SOCKET")
        self.interval = 0.0
        usec = os.environ.get("WATCHDOG_USEC")
        if usec:
            try:
                self.interval = int(usec) / 1000000.0
            except ValueError:
                self.interval = 0.0
        self._last = 0.0
        self.heartbeat_file = "/run/rasplayer/heartbeat"

    @property
    def enabled(self):
        return bool(self.address and self.interval > 0)

    def send(self, message):
        if not self.address:
            return False
        address = self.address
        if address.startswith("@"):
            address = "\0" + address[1:]
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                sock.sendto(message.encode("utf-8"), address)
            finally:
                sock.close()
            return True
        except OSError as exc:
            print("systemd notify failed: %s" % exc, flush=True)
            return False

    def ready(self):
        try:
            with open("/run/rasplayer/ready", "w") as stream:
                stream.write("1\n")
        except OSError:
            pass
        self.send("READY=1\nSTATUS=LOCAL_READY")

    def heartbeat(self):
        now = time.monotonic()
        try:
            with open(self.heartbeat_file, "w") as stream:
                stream.write("%.3f\n" % now)
        except OSError:
            pass
        if not self.enabled:
            return
        if now - self._last >= max(0.5, self.interval / 2.0):
            if self.send("WATCHDOG=1\nSTATUS=healthy"):
                self._last = now
