"""Small serialized command queue used by the GPIO-facing application."""
import queue
import threading


class SerializedCommandPath:
    def __init__(self, handler, tick=None, maxsize=64, tick_interval=0.05):
        self._handler = handler
        self._tick = tick
        self._queue = queue.Queue(maxsize=maxsize)
        self._tick_interval = tick_interval
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run,
                                            name="rasplayer-command-owner",
                                            daemon=True)
            self._thread.start()

    def submit(self, command, value=None):
        try:
            self._queue.put_nowait((command, value))
            return True
        except queue.Full:
            return False

    def _run(self):
        while True:
            try:
                command, value = self._queue.get(timeout=self._tick_interval)
            except queue.Empty:
                command = None
                value = None
            try:
                if command is not None:
                    self._handler(command, value)
                if self._tick is not None:
                    self._tick()
            except Exception as exc:
                print("Command failed (%s): %s" % (command, exc), flush=True)
            finally:
                if command is not None:
                    self._queue.task_done()

