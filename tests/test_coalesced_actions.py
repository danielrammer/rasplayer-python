import threading
import time
import unittest

from SoundPlayer import (
    FeedbackPlayer, SoundPlayerBase, apply_generic_input,
    make_generic_input_event, route_generic_input)


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
    class _EdgePlayer:
        def __init__(self):
            self.actions = []

        def buttonDown(self, button):
            self.actions.append(("press_action", button))
            return True

        def buttonUp(self, button):
            self.actions.append(("release_action", button))
            return True

    class _SynthEdgePlayer(_EdgePlayer):
        def buttonDown(self, button):
            self.actions.append(("note_on", button))
            return True

        def buttonUp(self, button):
            self.actions.append(("note_off", button))
            return True

    @staticmethod
    def event(pressed, button=2):
        return {
            "button": button,
            "channel": 6,
            "level": 1 if pressed else 0,
            "pressed": pressed,
            "edge": "press" if pressed else "release",
            "input_at": 1.0,
        }

    def test_callback_payload_captures_press_and_release_level(self):
        inputs = [11, 5, 6, 19, 16]
        press = make_generic_input_event(6, inputs, lambda channel: 1, 10.0)
        release = make_generic_input_event(6, inputs, lambda channel: 0, 11.0)
        self.assertEqual(
            (press["button"], press["edge"], press["level"], press["input_at"]),
            (2, "press", 1, 10.0))
        self.assertEqual(
            (release["button"], release["edge"], release["level"],
             release["input_at"]),
            (2, "release", 0, 11.0))

    def test_sampler_press_release_triggers_exactly_once(self):
        player = self._EdgePlayer()
        for event in (self.event(True), self.event(False)):
            command, payload = route_generic_input(
                event, "INSTRUMENT", True, 4)
            self.assertEqual(command, "generic")
            apply_generic_input(player, "INSTRUMENT", payload)
        self.assertEqual(player.actions, [("press_action", 2)])

    def test_music_playlist_press_release_selects_exactly_once(self):
        player = self._EdgePlayer()
        routed = [
            route_generic_input(event, "MUSIC", True, 7)
            for event in (self.event(True), self.event(False))]
        self.assertEqual(routed[0][0], "selection")
        self.assertIsNone(routed[1])
        player.buttonDown(routed[0][1]["button"])
        self.assertEqual(player.actions, [("press_action", 2)])

    def test_online_channel_press_release_selects_exactly_once(self):
        player = self._EdgePlayer()
        routed = [
            route_generic_input(event, "ONLINE", True, 8)
            for event in (self.event(True), self.event(False))]
        self.assertEqual(routed[0][0], "selection")
        self.assertIsNone(routed[1])
        player.buttonDown(routed[0][1]["button"])
        self.assertEqual(player.actions, [("press_action", 2)])

    def test_synth_press_release_is_note_on_then_note_off(self):
        player = self._SynthEdgePlayer()
        for event in (self.event(True), self.event(False)):
            command, payload = route_generic_input(event, "SYNTH", True, 9)
            self.assertEqual(command, "generic")
            apply_generic_input(player, "SYNTH", payload)
        self.assertEqual(
            player.actions, [("note_on", 2), ("note_off", 2)])

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
