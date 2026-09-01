import sys
import threading
import time
import types
import unittest


if "vlc" not in sys.modules:
    vlc = types.ModuleType("vlc")
    vlc.State = types.SimpleNamespace(
        Playing="playing", Error="error", Ended="ended", Stopped="stopped")
    sys.modules["vlc"] = vlc

from OnlinePlayer import OnlinePlayer
from command_path import SerializedCommandPath


class _FakeMedia:
    def __init__(self, url):
        self.url = url
        self.options = []

    def add_option(self, option):
        self.options.append(option)


class _FakeVlc:
    def media_new(self, url):
        return _FakeMedia(url)


class _FakePlayer:
    def __init__(self):
        self.media = None
        self.opened = []

    def set_media(self, media):
        self.media = media

    def play(self):
        self.opened.append(self.media.url)
        return 0


class OnlinePlayerPageTests(unittest.TestCase):
    def make_player(self):
        backend = _FakePlayer()
        player = OnlinePlayer(_FakeVlc(), backend, "")
        self.assertEqual(len(backend.opened), 1)
        return player, backend

    def test_three_page_wrapping(self):
        player, backend = self.make_player()
        player.navigate(-1)
        self.assertEqual(player.currentPage, 2)
        player.navigate(1)
        self.assertEqual(player.currentPage, 0)
        player.navigate(3)
        self.assertEqual(player.currentPage, 0)
        self.assertEqual(len(backend.opened), 1)

    def test_previous_and_next_only_change_page(self):
        player, backend = self.make_player()
        original_radio = player.currentRadio
        player.navigate(1)
        player.navigate(-1)
        self.assertEqual(player.currentRadio, original_radio)
        self.assertEqual(len(backend.opened), 1)

    def test_five_buttons_map_to_current_page(self):
        player, backend = self.make_player()
        for page in range(3):
            player.currentPage = page
            for button in range(5):
                self.assertTrue(player.buttonDown(button))
                expected = page * 5 + button
                self.assertEqual(player.currentRadio, expected)
                self.assertEqual(backend.opened[-1], player.radios[expected])

    def test_press_and_release_routes_one_selection(self):
        from SoundPlayer import route_generic_input

        player, backend = self.make_player()
        press = {"button": 3, "pressed": True}
        release = {"button": 3, "pressed": False}
        routed_press = route_generic_input(press, "ONLINE", True, 7)
        routed_release = route_generic_input(release, "ONLINE", True, 7)
        self.assertEqual(routed_press[0], "selection")
        self.assertIsNone(routed_release)
        player.buttonDown(routed_press[1]["button"])
        self.assertEqual(len(backend.opened), 2)

    def test_coalesced_rapid_page_changes_converge_on_final_page(self):
        player, backend = self.make_player()
        release = threading.Event()
        handled = []

        def handle(command, value):
            if command == "block":
                release.wait(1)
            elif command == "navigation_delta":
                handled.append(value)
                player.navigate(value)

        path = SerializedCommandPath(
            handle, tick_interval=0.005,
            coalesce={"navigation_delta": "sum"},
            logger=lambda message: None)
        path.start()
        self.addCleanup(path.close)
        path.submit("block")
        time.sleep(0.02)
        deltas = (1, 1, -1, 1, 1, 1, -1)
        for delta in deltas:
            path.submit("navigation_delta", delta)
        self.assertEqual(path.health()["queue_depth"], 1)
        release.set()
        deadline = time.time() + 1
        while not handled and time.time() < deadline:
            time.sleep(0.005)
        expected = 0
        for delta in deltas:
            expected = (expected + delta) % 3
        self.assertEqual(handled, [sum(deltas)])
        self.assertEqual(player.currentPage, expected)
        self.assertEqual(len(backend.opened), 1)

    def test_page_three_retains_original_five_stations(self):
        self.assertEqual(
            tuple(url for name, url in OnlinePlayer.stations[10:]),
            (
                "http://mp3channels.webradio.antenne.de/rockantenne",
                "http://mp3channels.webradio.antenne.de/80er-kulthits",
                "http://mp3channels.webradio.antenne.de/workout-hits",
                "http://mp3channels.webradio.antenne.de/chillout",
                "http://mp3channels.webradio.antenne.de/hitmix",
            ))

    def test_all_stations_are_direct_http_media_not_playlists(self):
        urls = tuple(url for _name, url in OnlinePlayer.stations)
        self.assertTrue(all(url.startswith("http://") for url in urls))
        self.assertTrue(all(not url.endswith(".pls") for url in urls))

    def test_slow_relays_have_nonblocking_twenty_second_open_window(self):
        self.assertEqual(OnlinePlayer.OPEN_TIMEOUT_SECONDS, 20.0)


if __name__ == "__main__":
    unittest.main()
