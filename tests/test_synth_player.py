import importlib
import sys
import threading
import types
import unittest


gpio = types.ModuleType("RPi.GPIO")
gpio.input = lambda _pin: 0
rpi = types.ModuleType("RPi")
rpi.GPIO = gpio
sys.modules.setdefault("RPi", rpi)
sys.modules.setdefault("RPi.GPIO", gpio)

SynthPlayer = importlib.import_module("SynthPlayer").SynthPlayer


class FakeFluidSynth:
    def __init__(self):
        self.calls = []

    def program_select(self, channel, sfid, bank, instrument):
        self.calls.append(("program_select", channel, sfid, bank, instrument))
        return 0

    def noteon(self, channel, midi_note, velocity):
        self.calls.append(("noteon", channel, midi_note, velocity))
        return 0

    def noteoff(self, channel, midi_note):
        self.calls.append(("noteoff", channel, midi_note))
        return 0


class SynthButtonTest(unittest.TestCase):
    def make_player(self):
        player = SynthPlayer.__new__(SynthPlayer)
        player.fs = FakeFluidSynth()
        player.sfid = 1
        player.instrument = 81
        player.generic_inputs = [11, 5, 6, 19, 16]
        player.min_freq = 130
        player.min_distance = 5
        player.max_distance = 35
        player.half_tone_ratio = 2 ** (1 / 12)
        player.current_note = None
        player._distance = -1.0
        player._latest_valid_distance = 5.0
        player._latest_valid_at = 0.0
        player._distance_lock = threading.Lock()
        player._button_latched_until = 0.0
        player._last_control_log = 0.0
        player._last_control_midi = None
        return player

    def test_generic_event_calls_noteon_even_without_current_sensor_sample(self):
        player = self.make_player()

        player.buttonDown(0)

        self.assertEqual(
            player.fs.calls,
            [("program_select", 0, 1, 0, 86),
             ("noteon", 0, 47, 120)])
        self.assertEqual(player.current_note, 47)

    def test_historical_two_centimeter_bin_does_not_retrigger_within_step(self):
        player = self.make_player()
        player._note_on(5.10, "test", raw_distance=5.10)
        player._note_on(6.99, "test", raw_distance=6.99)
        player._note_on(7.01, "test", raw_distance=7.01)

        note_calls = [call for call in player.fs.calls if call[0] == "noteon"]
        self.assertEqual(note_calls,
                         [("noteon", 0, 47, 120),
                          ("noteon", 0, 48, 120)])


if __name__ == "__main__":
    unittest.main()
