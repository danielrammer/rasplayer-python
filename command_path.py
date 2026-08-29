"""Small serialized command queue used by the GPIO-facing application."""
import queue
import threading
import time


class SerializedCommandPath:
    def __init__(self, handler, tick=None, maxsize=64, tick_interval=0.05,
                 logger=None):
        self._handler = handler
        self._tick = tick
        self._queue = queue.Queue(maxsize=maxsize)
        self._tick_interval = tick_interval
        self._thread = None
        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._logger = logger or self._default_logger

    @staticmethod
    def _default_logger(message):
        print(message, flush=True)

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run,
                                            name="rasplayer-command-owner",
                                            daemon=True)
            self._thread.start()

    def submit(self, command, value=None):
        enqueued_at = time.monotonic()
        with self._sequence_lock:
            self._sequence += 1
            sequence = self._sequence
        try:
            self._queue.put_nowait((sequence, command, value, enqueued_at))
            return True
        except queue.Full:
            self._logger(
                "COMMAND drop seq=%d command=%s enqueue=%.6f reason=queue_full"
                % (sequence, command, enqueued_at))
            return False

    def _run(self):
        while True:
            try:
                sequence, command, value, enqueued_at = self._queue.get(
                    timeout=self._tick_interval)
            except queue.Empty:
                sequence = None
                command = None
                value = None
                enqueued_at = None
            result = "ok"
            handler_started = None
            try:
                if command is not None:
                    dequeued_at = time.monotonic()
                    handler_started = dequeued_at
                    self._logger(
                        "COMMAND dequeue seq=%d command=%s enqueue=%.6f "
                        "dequeue=%.6f queue_wait_ms=%.3f depth=%d"
                        % (sequence, command, enqueued_at, dequeued_at,
                           (dequeued_at - enqueued_at) * 1000.0,
                           self._queue.qsize()))
                    self._handler(command, value)
            except Exception as exc:
                result = "error"
                self._logger("COMMAND exception seq=%s command=%s error=%r"
                             % (sequence, command, exc))
            finally:
                if command is not None:
                    completed_at = time.monotonic()
                    self._logger(
                        "COMMAND complete seq=%d command=%s complete=%.6f "
                        "handler_ms=%.3f result=%s"
                        % (sequence, command, completed_at,
                           (completed_at - handler_started) * 1000.0,
                           result))
                    self._queue.task_done()

            if self._tick is not None:
                tick_started = time.monotonic()
                try:
                    self._tick()
                except Exception as exc:
                    self._logger("COMMAND tick_exception error=%r" % (exc,))
                tick_ms = (time.monotonic() - tick_started) * 1000.0
                if tick_ms >= 25.0:
                    self._logger("COMMAND slow_tick duration_ms=%.3f" % tick_ms)
