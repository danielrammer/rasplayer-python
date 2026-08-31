import time
import threading
import unittest

from command_path import SerializedCommandPath


class SerializedCommandPathTests(unittest.TestCase):
    def start_path(self, *args, **kwargs):
        path = SerializedCommandPath(*args, **kwargs)
        path.start()
        self.addCleanup(path.close)
        return path

    def test_preserves_order_and_survives_handler_failure(self):
        seen = []

        def handler(command, value):
            seen.append((command, value))
            if command == "bad":
                raise RuntimeError("expected")

        path = self.start_path(
            handler, maxsize=8, tick_interval=0.01, logger=lambda message: None)
        self.assertTrue(path.submit("first", 1))
        self.assertTrue(path.submit("bad"))
        self.assertTrue(path.submit("last", 3))
        deadline = time.time() + 1
        while len(seen) < 3 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(seen, [("first", 1), ("bad", None), ("last", 3)])

    def test_queue_is_bounded(self):
        path = SerializedCommandPath(
            lambda c, v: None, maxsize=1, logger=lambda message: None)
        self.assertTrue(path.submit("one"))
        self.assertFalse(path.submit("two"))
        path.close()

    def test_accumulates_pending_delta_and_opposing_inputs_cancel(self):
        seen = []
        path = SerializedCommandPath(
            lambda command, value: seen.append((command, value)),
            coalesce={"volume_delta": "sum"}, logger=lambda message: None)
        self.assertTrue(path.submit("volume_delta", 10))
        self.assertTrue(path.submit("volume_delta", 10))
        self.assertTrue(path.submit("volume_delta", -10))
        self.assertEqual(path.health()["queue_depth"], 1)
        path.start()
        self.addCleanup(path.close)
        deadline = time.time() + 1
        while not seen and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(seen, [("volume_delta", 10)])
        self.assertEqual(path.health()["coalesced"], 2)

        cancelled = SerializedCommandPath(
            lambda command, value: None,
            coalesce={"navigation_delta": "sum"},
            logger=lambda message: None)
        self.assertTrue(cancelled.submit("navigation_delta", 1))
        self.assertTrue(cancelled.submit("navigation_delta", -1))
        self.assertEqual(cancelled.health()["queue_depth"], 0)
        self.assertEqual(cancelled.health()["cancelled"], 1)
        cancelled.close()

    def test_latest_replaces_only_matching_pending_command(self):
        seen = []
        path = SerializedCommandPath(
            lambda command, value: seen.append((command, value)),
            coalesce={"mode": "latest"}, logger=lambda message: None)
        path.submit("mode", "music")
        path.submit("safety", "keep")
        path.submit("mode", "online")
        path.start()
        self.addCleanup(path.close)
        deadline = time.time() + 1
        while len(seen) < 2 and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(seen, [("safety", "keep"), ("mode", "online")])
        self.assertEqual(path.health()["superseded"], 1)

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

        path = self.start_path(
            handler, tick_interval=0.005, logger=lambda message: None)
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

        path = self.start_path(
            handler, tick_interval=0.005, logger=lambda message: None)
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

        path = self.start_path(
            handler, maxsize=64, tick_interval=0.005,
            logger=lambda message: None)
        for mode_number in range(20):
            self.assertTrue(path.submit("mode", mode_number))
            self.assertTrue(path.submit("input", time.monotonic()))
        self.assertTrue(completed.wait(1.0))
        self.assertLess(max(input_waits_ms), 100.0)

    def test_blocked_owner_leaves_only_one_latest_action_per_category(self):
        release = threading.Event()
        seen = []

        def handler(command, value):
            if command == "block":
                release.wait(1)
            else:
                seen.append((command, value, time.monotonic()))

        path = self.start_path(
            handler, tick_interval=0.005,
            coalesce={
                "volume_delta": "sum",
                "navigation_delta": "sum",
                "selection": "latest",
                "mode": "latest",
            }, logger=lambda message: None)
        path.submit("block")
        time.sleep(0.02)
        for index in range(100):
            path.submit("volume_delta", 10 if index % 3 else -10)
            path.submit("navigation_delta", 1)
            path.submit("selection", index % 5)
            path.submit("mode", index % 4)
        self.assertEqual(path.health()["queue_depth"], 4)
        released_at = time.monotonic()
        release.set()
        deadline = time.time() + 1
        while len(seen) < 4 and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(seen), 4)
        self.assertLess((seen[-1][2] - released_at) * 1000.0, 100.0)
        self.assertEqual(path.health()["dropped"], 0)


if __name__ == "__main__":
    unittest.main()
