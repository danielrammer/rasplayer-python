import sys
import types
import unittest


if "RPi.GPIO" not in sys.modules:
    gpio = types.ModuleType("RPi.GPIO")
    gpio.input = lambda _pin: 0
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    sys.modules["RPi"] = rpi
    sys.modules["RPi.GPIO"] = gpio

from MusicPlayer import MusicPlayer
from SoundPlayer import SoundPlayerBase


class MusicPlayerEventTests(unittest.TestCase):
    def test_natural_track_end_uses_silent_automatic_command(self):
        dispatched = []
        original = SoundPlayerBase.input_dispatcher
        SoundPlayerBase.input_dispatcher = (
            lambda command, value=None: dispatched.append((command, value)))
        self.addCleanup(
            setattr, SoundPlayerBase, "input_dispatcher", original)

        player = object.__new__(MusicPlayer)
        player._on_song_end(None)

        self.assertEqual(dispatched, [("automatic_next", None)])


if __name__ == "__main__":
    unittest.main()
