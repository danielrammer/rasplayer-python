"""Small serialized command queue used by the GPIO-facing application."""
from collections import deque
import threading
import time


class SerializedCommandPath:
    """Single-owner command path with opt-in, per-command coalescing."""

    def __init__(self, handler, tick=None, maxsize=64, tick_interval=0.05,
                 logger=None, coalesce=None):
        self._handler = handler
        self._tick = tick
        self._maxsize = maxsize
        self._pending = deque()
        self._condition = threading.Condition()
        self._tick_interval = tick_interval
        self._thread = None
        self._sequence = 0
        self._logger = logger or self._default_logger
        self._last_tick_completed_at = 0.0
        self._last_dequeue_at = 0.0
        self._coalesce = dict(coalesce or {})
        self._coalesced = 0
        self._cancelled = 0
        self._superseded = 0
        self._dropped = 0
        self._stop = False

    @staticmethod
    def _default_logger(message):
        print(message, flush=True)

    def start(self):
        with self._condition:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="rasplayer-command-owner",
                    daemon=True)
                self._thread.start()

    def close(self, timeout=1.0):
        """Stop the owner thread. Production normally exits with the process."""
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _find_pending(self, command):
        for entry in self._pending:
            if entry["command"] == command:
                return entry
        return None

    def submit(self, command, value=None):
        enqueued_at = time.monotonic()
        with self._condition:
            self._sequence += 1
            sequence = self._sequence
            policy = self._coalesce.get(command)
            existing = self._find_pending(command) if policy else None
            if existing is not None:
                old_sequence = existing["sequence"]
                existing["sequence"] = sequence
                existing["last_enqueued_at"] = enqueued_at
                existing["input_count"] += 1
                self._coalesced += 1
                outcome = "combined"
                if policy == "sum":
                    existing["value"] += value
                    if existing["value"] == 0:
                        self._pending.remove(existing)
                        self._cancelled += 1
                        outcome = "cancelled"
                    else:
                        # The combined intent belongs at the newest input's
                        # position; unrelated pending commands keep FIFO order.
                        self._pending.remove(existing)
                        self._pending.append(existing)
                elif policy == "latest":
                    existing["value"] = value
                    self._superseded += 1
                    outcome = "superseded"
                    self._pending.remove(existing)
                    self._pending.append(existing)
                else:
                    raise ValueError("unknown coalescing policy %r" % policy)
                self._logger(
                    "COMMAND coalesce command=%s old_seq=%d new_seq=%d "
                    "policy=%s outcome=%s value=%r depth=%d coalesced=%d "
                    "cancelled=%d superseded=%d"
                    % (command, old_sequence, sequence, policy, outcome,
                       existing["value"], len(self._pending), self._coalesced,
                       self._cancelled, self._superseded))
                self._condition.notify()
                return True

            if len(self._pending) >= self._maxsize:
                self._dropped += 1
                self._logger(
                    "COMMAND drop seq=%d command=%s enqueue=%.6f "
                    "reason=queue_full depth=%d dropped=%d"
                    % (sequence, command, enqueued_at, len(self._pending),
                       self._dropped))
                return False

            self._pending.append({
                "sequence": sequence,
                "command": command,
                "value": value,
                "first_enqueued_at": enqueued_at,
                "last_enqueued_at": enqueued_at,
                "input_count": 1,
            })
            depth = len(self._pending)
            self._logger(
                "COMMAND enqueue seq=%d command=%s enqueue=%.6f depth=%d"
                % (sequence, command, enqueued_at, depth))
            self._condition.notify()
            return True

    def health(self):
        """Return a diagnostic snapshot for lightweight producers."""
        now = time.monotonic()
        last_tick = self._last_tick_completed_at
        with self._condition:
            depth = len(self._pending)
            coalesced = self._coalesced
            cancelled = self._cancelled
            superseded = self._superseded
            dropped = self._dropped
        return {
            "owner_alive": self._thread is not None and self._thread.is_alive(),
            "queue_depth": depth,
            "heartbeat_age_ms": ((now - last_tick) * 1000.0
                                 if last_tick else -1.0),
            "last_dequeue_age_ms": ((now - self._last_dequeue_at) * 1000.0
                                    if self._last_dequeue_at else -1.0),
            "coalesced": coalesced,
            "cancelled": cancelled,
            "superseded": superseded,
            "dropped": dropped,
        }

    def _next(self):
        with self._condition:
            if not self._pending and not self._stop:
                self._condition.wait(self._tick_interval)
            if self._stop:
                return None
            return self._pending.popleft() if self._pending else {}

    def _run(self):
        while True:
            entry = self._next()
            if entry is None:
                return
            command = entry.get("command")
            result = "ok"
            handler_started = None
            try:
                if command is not None:
                    dequeued_at = time.monotonic()
                    self._last_dequeue_at = dequeued_at
                    handler_started = dequeued_at
                    with self._condition:
                        depth = len(self._pending)
                    self._logger(
                        "COMMAND dequeue seq=%d command=%s first_enqueue=%.6f "
                        "last_enqueue=%.6f dequeue=%.6f oldest_wait_ms=%.3f "
                        "queue_wait_ms=%.3f depth=%d input_count=%d"
                        % (entry["sequence"], command,
                           entry["first_enqueued_at"],
                           entry["last_enqueued_at"], dequeued_at,
                           (dequeued_at - entry["first_enqueued_at"]) * 1000.0,
                           (dequeued_at - entry["last_enqueued_at"]) * 1000.0,
                           depth, entry["input_count"]))
                    self._handler(command, entry["value"])
            except Exception as exc:
                result = "error"
                self._logger("COMMAND exception seq=%s command=%s error=%r"
                             % (entry.get("sequence"), command, exc))
            finally:
                if command is not None:
                    completed_at = time.monotonic()
                    self._logger(
                        "COMMAND complete seq=%d command=%s complete=%.6f "
                        "handler_ms=%.3f action_latency_ms=%.3f result=%s"
                        % (entry["sequence"], command, completed_at,
                           (completed_at - handler_started) * 1000.0,
                           (completed_at - entry["last_enqueued_at"]) * 1000.0,
                           result))

            if self._tick is not None:
                tick_started = time.monotonic()
                try:
                    self._tick()
                except Exception as exc:
                    self._logger("COMMAND tick_exception error=%r" % (exc,))
                self._last_tick_completed_at = time.monotonic()
                tick_ms = (self._last_tick_completed_at - tick_started) * 1000.0
                if tick_ms >= 25.0:
                    self._logger("COMMAND slow_tick duration_ms=%.3f" % tick_ms)
