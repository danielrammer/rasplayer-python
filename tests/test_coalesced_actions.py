import threading
import time
import unittest

from SoundPlayer import FeedbackPlayer, SoundPlayerBase


class _FakeMediaPlayer:
    def __init__(self):
        self.media = None
        self.play_calls = 0

    def set_media(self, media):
        self.media = media

    def play(self):
        self.play_calls += 1
        return 0


class _FakeVlc:
    def media_new(self, value):
        return "media:" + value


class _FakeProcess:
    returncode = 0

    def __init__(self, release):
        self._release = release
        self._done = False

    def communicate(self, timeout=None):
        self._release.wait(timeout)
        self._done = True
        return b"", b""

    def poll(self):
        return 0 if self._done else None

    def terminate(self):
        self._release.set()

    def kill(self):
        self._release.set()


class CoalescedActionTests(unittest.TestCase):
    def test_base_navigation_opens_only_final_item(self):
        backend = _FakeMediaPlayer()
        player = SoundPlayerBase(_FakeVlc(), backend, "")
        player.filelist = ["a", "b", "c", "d"]
        player.numberOfItemsInList = len(player.filelist)
        player.currentFileNum = 0

        self.assertTrue(player.navigate(11))
        self.assertEqual(player.currentFileNum, 3)
        self.assertEqual(backend.media, "media:d")
        self.assertEqual(backend.play_calls, 1)

    def test_feedback_keeps_only_latest_pending_category(self):
        release_first = threading.Event()
        first_started = threading.Event()
        created = []

        def factory(*args, **kwargs):
            release = release_first if not created else threading.Event()
            if created:
                release.set()
            process = _FakeProcess(release)
            created.append(process)
            first_started.set()
            return process

        feedback = FeedbackPlayer(process_factory=factory)
        self.addCleanup(feedback.close)
        feedback.play("generic", source="first", category="mode")
        self.assertTrue(first_started.wait(0.5))
        for index in range(20):
            feedback.play("generic", source="mode-%d" % index,
                          category="mode")
        with feedback._request_condition:
            self.assertEqual(len(feedback._requests), 1)
            self.assertEqual(feedback._requests[0][5], "mode-19")
        release_first.set()
        deadline = time.time() + 1
        while len(created) < 2 and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(created), 2)


if __name__ == "__main__":
    unittest.main()
