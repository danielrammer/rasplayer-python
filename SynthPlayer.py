import RPi.GPIO as GPIO
from SoundPlayer import SoundPlayerBase
import numpy as np
import fluidsynth


class SynthPlayer(SoundPlayerBase):

    def __init__(self, vlcInstance, player, path, get_distance_func):

        SoundPlayerBase.__init__(self, vlcInstance, player, path)

        self.get_distance = get_distance_func

        self.is_playing = True
        self.frequency = 440
        self.current_note = None

        # Frequency mapping
        self.min_freq = 130
        self.max_freq = 1000
        self.min_distance = 5
        self.max_distance = 35
        self.half_tone_ratio = 2 ** (1/12)
        self.last_valid_distance = self.min_distance

        # Button pins
        self.generic_inputs = [11,5,6,19,16]

        # --- FluidSynth setup ---
        self.fs = fluidsynth.Synth()
        self.fs.start(driver="alsa")

        soundfont = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
        self.sfid = self.fs.sfload(soundfont)

        # channel, sfid, bank, preset
        self.instrument = 81  # synth lead
        self.fs.program_select(0, self.sfid, 0, self.instrument)

        self.button_held = False
        self.in_range = False

    # --------------------------------------------------

    def freq_to_midi(self, freq):
        return int(69 + 12 * np.log2(freq / 440.0))

    # --------------------------------------------------

    def update(self):

        distance = self.get_distance()

        if distance > 0 and self.min_distance <= distance <= self.max_distance:
            self.last_valid_distance = distance

        step = int((self.last_valid_distance - self.min_distance) // 2)
        self.frequency = self.min_freq * (self.half_tone_ratio ** step)

        self.in_range = distance > 0

        # print(
        #     f"D:{distance:.2f}cm Last:{self.last_valid_distance:.2f} "
        #     f"Step:{step} F:{self.frequency:.2f}"
        # )

        self.button_held = any(GPIO.input(pin) for pin in self.generic_inputs)

        if not (self.button_held and self.in_range):
            if self.current_note is not None:
                self.fs.noteoff(0, self.current_note)
                self.current_note = None
            return

        midi_note = self.freq_to_midi(self.frequency)

        if midi_note != self.current_note:

            if self.current_note is not None:
                self.fs.noteoff(0, self.current_note)

            self.fs.noteon(0, midi_note, 120)
            self.current_note = midi_note

    # --------------------------------------------------

    def buttonDown(self, buttonNumber):

        instruments = [81, 82, 83, 84, 85]  # different synth leads
        self.instrument = instruments[buttonNumber % len(instruments)]

        self.fs.program_select(0, self.sfid, 0, self.instrument)

        # print("Instrument changed:", self.instrument)

    # --------------------------------------------------

    def stop(self):

        if self.current_note is not None:
            self.fs.noteoff(0, self.current_note)

        self.fs.delete()

        self.is_playing = False