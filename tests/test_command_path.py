import time
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


if __name__ == "__main__":
    unittest.main()
