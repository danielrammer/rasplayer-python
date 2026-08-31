import threading
import time
import unittest

from SoundPlayer import FeedbackPlayer


class FakeProcess:
    returncode = 0

    def communicate(self, timeout=None):
        return b"", b""

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class FeedbackPlayerTest(unittest.TestCase):
    def test_enqueue_is_nonblocking_and_uses_generic_asset(self):
        calls = []
        called = threading.Event()

        def process_factory(command, **kwargs):
            calls.append((command, kwargs))
            called.set()
            return FakeProcess()

        feedback = FeedbackPlayer(process_factory=process_factory)
        try:
            started = time.monotonic()
            self.assertTrue(feedback.play("generic", source="mode_TEST"))
            self.assertLess(time.monotonic() - started, 0.05)
            self.assertTrue(called.wait(0.5))
            self.assertEqual(
                calls[0][0],
                ["mpg123", "-q", "-o", "alsa",
                 "./Sounds/System/0/generic.mp3"])
        finally:
            feedback.close()

    def test_unknown_feedback_is_rejected(self):
        feedback = FeedbackPlayer(process_factory=lambda *_a, **_k: FakeProcess())
        try:
            self.assertFalse(feedback.play("not-allowlisted"))
        finally:
            feedback.close()


if __name__ == "__main__":
    unittest.main()
