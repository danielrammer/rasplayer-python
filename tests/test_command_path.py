import time
import threading
import unittest

from command_path import SerializedCommandPath


class SerializedCommandPathTests(unittest.TestCase):
    def test_preserves_order_and_survives_handler_failure(self):
        seen = []

        def handler(command, value):
            seen.append((command, value))
            if command == "bad":
                raise RuntimeError("expected")

        path = SerializedCommandPath(handler, maxsize=8, tick_interval=0.01)
        path.start()
        self.assertTrue(path.submit("first", 1))
        self.assertTrue(path.submit("bad"))
        self.assertTrue(path.submit("last", 3))
        deadline = time.time() + 1
        while len(seen) < 3 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(seen, [("first", 1), ("bad", None), ("last", 3)])

    def test_queue_is_bounded(self):
        path = SerializedCommandPath(lambda c, v: time.sleep(0.2), maxsize=1)
        self.assertTrue(path.submit("one"))
        self.assertFalse(path.submit("two"))

    def test_slow_backend_work_does_not_delay_following_input_when_delegated(self):
        handled = []
        completed = threading.Event()

        def handler(command, value):
            if command == "mode":
                threading.Thread(target=lambda: time.sleep(0.30),
                                 daemon=True).start()
            else:
                handled.append((command, time.monotonic()))
                completed.set()

        path = SerializedCommandPath(handler, tick_interval=0.005)
        path.start()
        path.submit("mode")
        submitted = time.monotonic()
        path.submit("volume_up")
        self.assertTrue(completed.wait(0.15))
        self.assertLess((handled[0][1] - submitted) * 1000.0, 100.0)

    def test_synchronous_backend_work_demonstrates_previous_queue_delay(self):
        handled = []
        completed = threading.Event()

        def handler(command, value):
            if command == "mode":
                time.sleep(0.20)
            else:
                handled.append((command, time.monotonic()))
                completed.set()

        path = SerializedCommandPath(handler, tick_interval=0.005)
        path.start()
        path.submit("mode")
        submitted = time.monotonic()
        path.submit("volume_up")
        self.assertTrue(completed.wait(0.50))
        self.assertGreaterEqual((handled[0][1] - submitted) * 1000.0, 180.0)

    def test_repeated_async_mode_switches_keep_input_queue_latency_bounded(self):
        input_waits_ms = []
        completed = threading.Event()

        def handler(command, value):
            if command == "mode":
                threading.Thread(target=lambda: time.sleep(0.25),
                                 daemon=True).start()
            else:
                input_waits_ms.append((time.monotonic() - value) * 1000.0)
                if len(input_waits_ms) == 20:
                    completed.set()

        path = SerializedCommandPath(handler, maxsize=64, tick_interval=0.005)
        path.start()
        for mode_number in range(20):
            self.assertTrue(path.submit("mode", mode_number))
            self.assertTrue(path.submit("input", time.monotonic()))
        self.assertTrue(completed.wait(1.0))
        self.assertLess(max(input_waits_ms), 100.0)


if __name__ == "__main__":
    unittest.main()
