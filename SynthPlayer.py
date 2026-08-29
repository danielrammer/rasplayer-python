import RPi.GPIO as GPIO
import time
from SoundPlayer import SoundPlayerBase


class SynthPlayer(SoundPlayerBase):

    def __init__(self, vlcInstance, player, path, get_distance_func):

        SoundPlayerBase.__init__(self, vlcInstance, player, path)

        self.get_distance = get_distance_func

        self.is_playing = True
        self.frequency = 440
        self.current_note = None
        self.lastStep = -1

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
        import fluidsynth
        init_started = time.monotonic()
        self.fs = fluidsynth.Synth()
        try:
            # --- safer audio settings for Raspberry Pi ---
            self.fs.setting("audio.period-size", 1024)
            self.fs.setting("synth.polyphony", 64)
            self.fs.setting("audio.periods", 4)
            self.fs.setting("audio.alsa.device", "default")

            audio_started = time.monotonic()
            self.fs.start(driver="alsa")
            print("SYNTH audio_start_complete uptime=%.6f duration_ms=%.3f" %
                  (time.monotonic(),
                   (time.monotonic() - audio_started) * 1000.0), flush=True)

            soundfont = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
            sf_started = time.monotonic()
            self.sfid = self.fs.sfload(soundfont)
            print("SYNTH soundfont_load_complete uptime=%.6f duration_ms=%.3f sfid=%s" %
                  (time.monotonic(),
                   (time.monotonic() - sf_started) * 1000.0, self.sfid),
                  flush=True)
            if self.sfid < 0:
                raise RuntimeError("FluidSynth failed to load %s" % soundfont)

            # channel, sfid, bank, preset
            self.instrument = 81  # synth lead
            result = self.fs.program_select(0, self.sfid, 0, self.instrument)
            if result < 0:
                raise RuntimeError("FluidSynth initial program_select failed")
            print("SYNTH init_complete uptime=%.6f duration_ms=%.3f" %
                  (time.monotonic(),
                   (time.monotonic() - init_started) * 1000.0), flush=True)
        except Exception:
            print("SYNTH init_exception uptime=%.6f duration_ms=%.3f" %
                  (time.monotonic(),
                   (time.monotonic() - init_started) * 1000.0), flush=True)
            try:
                self.fs.stop()
            except Exception:
                pass
            try:
                self.fs.delete()
            except Exception:
                pass
            self.fs = None
            raise

        self.button_held = False
        self.in_range = False

    # --------------------------------------------------

    def freq_to_midi(self, freq):
        import numpy as np
        return int(69 + 12 * np.log2(freq / 440.0))

    # --------------------------------------------------

    def update(self):
        update_started = time.monotonic()
        distance = self.get_distance()
        distance_ms = (time.monotonic() - update_started) * 1000.0
        if distance_ms >= 25.0:
            print("SYNTH ultrasonic_slow uptime=%.6f duration_ms=%.3f distance=%.3f" %
                  (time.monotonic(), distance_ms, distance), flush=True)
        # print("got distance function:", distance)

        if distance > 0 and self.min_distance <= distance <= self.max_distance:
            self.last_valid_distance = distance

        step = int((self.last_valid_distance - self.min_distance) // 2)
        # if step == self.lastStep:
        #     return
        
        self.frequency = self.min_freq * (self.half_tone_ratio ** step)

        self.in_range = distance > 0

        # self.lastStep = step

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

        instruments = [86, 80, 71, 93, 19]
        self.instrument = instruments[buttonNumber % len(instruments)]

        self.fs.program_select(0, self.sfid, 0, self.instrument)

        # print("Instrument changed:", self.instrument)

    # --------------------------------------------------

    def stop(self):
        if self.fs is None:
            self.is_playing = False
            return
        if self.current_note is not None:
            try:
                self.fs.noteoff(0, self.current_note)
            except Exception:
                pass
        try:
            self.fs.stop()
        except Exception:
            pass
        try:
            self.fs.delete()
        finally:
            self.fs = None
        self.is_playing = False
