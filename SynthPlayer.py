import mmap
import math
import os
import struct
import threading
import time

import RPi.GPIO as GPIO

from SoundPlayer import SoundPlayerBase


class _UltrasonicSensor:
    """HC-SR04 measurement using the same GPIO register path as the proven test."""

    _GPIO_MAP_SIZE = 4096
    _GPFSEL1 = 0x04
    _GPSET0 = 0x1c
    _GPCLR0 = 0x28
    _GPLEV0 = 0x34
    _ECHO_TIMEOUT_NS = 30_000_000

    def __init__(self, trigger_pin, echo_pin):
        if not (0 <= trigger_pin < 32 and 0 <= echo_pin < 32):
            raise ValueError("ultrasonic pins must be in GPIO bank 0")
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        fd = os.open("/dev/gpiomem", os.O_RDWR | os.O_SYNC)
        try:
            self._gpio = mmap.mmap(
                fd, self._GPIO_MAP_SIZE, flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE)
        finally:
            os.close(fd)

        trigger_shift = (trigger_pin % 10) * 3
        echo_shift = (echo_pin % 10) * 3
        mode_mask = (7 << trigger_shift) | (7 << echo_shift)
        self._original_fsel = self._read_register(self._GPFSEL1)
        configured_fsel = self._original_fsel & ~mode_mask
        configured_fsel |= 1 << trigger_shift
        self._write_register(self._GPFSEL1, configured_fsel)
        observed_fsel = self._read_register(self._GPFSEL1)
        print("SYNTH ultrasonic_gpio_config before=0x%08x after=0x%08x "
              "expected=0x%08x" %
              (self._original_fsel, observed_fsel, configured_fsel),
              flush=True)
        self._write_trigger(False)
        time.sleep(0.002)

    def _read_register(self, offset):
        return struct.unpack_from("<I", self._gpio, offset)[0]

    def _write_register(self, offset, value):
        struct.pack_into("<I", self._gpio, offset, value)

    def _write_trigger(self, high):
        self._write_register(
            self._GPSET0 if high else self._GPCLR0,
            1 << self.trigger_pin)

    def echo_level(self):
        value = self._read_register(self._GPLEV0)
        return 1 if value & (1 << self.echo_pin) else 0

    def _wait_for_echo(self, expected, cooperative):
        deadline = time.monotonic_ns() + self._ECHO_TIMEOUT_NS
        spins = 0
        while True:
            if self.echo_level() == expected:
                return time.monotonic_ns()
            if time.monotonic_ns() >= deadline:
                return None
            spins += 1
            if cooperative and spins % 64 == 0:
                # Release the GIL without adding an unbounded sleep. Direct
                # polling while waiting for a missing start edge previously
                # delayed the serialized command owner. Do not yield while
                # timing the HIGH pulse: scheduler delay corrupts distance.
                time.sleep(0)

    def measure(self):
        measurement_started = time.monotonic_ns()
        self._write_trigger(False)
        time.sleep(0.000002)
        self._write_trigger(True)
        time.sleep(0.000010)
        self._write_trigger(False)

        pulse_start = self._wait_for_echo(1, cooperative=True)
        if pulse_start is None:
            elapsed_ms = (time.monotonic_ns() - measurement_started) / 1e6
            return -1.0, "start", elapsed_ms
        pulse_end = self._wait_for_echo(0, cooperative=False)
        if pulse_end is None:
            elapsed_ms = (time.monotonic_ns() - measurement_started) / 1e6
            return -1.0, "end", elapsed_ms

        pulse_us = (pulse_end - pulse_start) / 1000.0
        elapsed_ms = (time.monotonic_ns() - measurement_started) / 1e6
        return pulse_us * 0.0343 / 2.0, None, elapsed_ms

    def close(self):
        try:
            self._write_trigger(False)
            self._write_register(self._GPFSEL1, self._original_fsel)
        finally:
            self._gpio.close()


class SynthPlayer(SoundPlayerBase):

    def __init__(self, vlcInstance, player, path, trigger_pin, echo_pin):
        SoundPlayerBase.__init__(self, vlcInstance, player, path)

        self.is_playing = True
        self.frequency = 440
        self.current_note = None
        self.lastStep = -1

        self.min_freq = 130
        self.max_freq = 1000
        self.min_distance = 5
        self.max_distance = 35
        self.half_tone_ratio = 2 ** (1/12)
        self.last_valid_distance = self.min_distance

        self.generic_inputs = [11, 5, 6, 19, 16]
        self.button_held = False
        self.in_range = False

        self._distance = -1.0
        self._latest_valid_distance = self.min_distance
        self._latest_valid_at = 0.0
        self._distance_lock = threading.Lock()
        self._measurement_stop = threading.Event()
        self._measurement_thread = None
        self._sensor = None
        self._last_note_log = 0.0
        self._last_control_log = 0.0
        self._last_control_midi = None
        self._button_latched_until = 0.0
        self._pressed_buttons = set()

        import fluidsynth
        init_started = time.monotonic()
        self.fs = fluidsynth.Synth()
        try:
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

            self.instrument = 81
            result = self.fs.program_select(0, self.sfid, 0, self.instrument)
            if result < 0:
                raise RuntimeError("FluidSynth initial program_select failed")

            # RasPlayer configures BCM14 as output and BCM15 as input. Accessing
            # /dev/gpiomem here matches the physically proven diagnostic's I/O path.
            self._sensor = _UltrasonicSensor(trigger_pin, echo_pin)
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
            if self._sensor is not None:
                try:
                    self._sensor.close()
                except Exception:
                    pass
                self._sensor = None
            self.fs = None
            raise

        self._measurement_thread = threading.Thread(
            target=self._measurement_worker,
            name="rasplayer-ultrasonic", daemon=True)
        self._measurement_thread.start()

    def _measurement_worker(self):
        measurement_count = 0
        timeout_count = 0
        invalid_count = 0
        last_timeout_log = 0.0
        last_invalid_log = 0.0
        last_valid_log = 0.0
        last_logged_distance = None
        try:
            while not self._measurement_stop.is_set():
                distance, timeout_phase, duration_ms = self._sensor.measure()
                measurement_count += 1
                now = time.monotonic()
                with self._distance_lock:
                    self._distance = distance
                    if self.min_distance <= distance <= self.max_distance:
                        self._latest_valid_distance = distance
                        self._latest_valid_at = now

                if timeout_phase is not None:
                    timeout_count += 1
                    if now - last_timeout_log >= 5.0:
                        print(
                            "SYNTH ultrasonic_timeout phase=%s count=%d "
                            "measurement=%d duration_ms=%.3f echo=%d" %
                            (timeout_phase, timeout_count, measurement_count,
                             duration_ms, self._sensor.echo_level()),
                            flush=True)
                        last_timeout_log = now
                elif not (self.min_distance <= distance <= self.max_distance):
                    invalid_count += 1
                    if now - last_invalid_log >= 5.0:
                        print(
                            "SYNTH ultrasonic_invalid count=%d measurement=%d "
                            "distance_cm=%.2f duration_ms=%.3f" %
                            (invalid_count, measurement_count, distance,
                             duration_ms), flush=True)
                        last_invalid_log = now
                elif (now - last_valid_log >= 1.0 or
                      (now - last_valid_log >= 0.25 and
                       (last_logged_distance is None or
                        abs(distance - last_logged_distance) >= 1.0))):
                    print(
                        "SYNTH ultrasonic_valid measurement=%d "
                        "distance_cm=%.2f duration_ms=%.3f" %
                        (measurement_count, distance, duration_ms), flush=True)
                    last_valid_log = now
                    last_logged_distance = distance

                # Commit 5d73c6e deliberately changed the playable Synth loop
                # to 100 ms. Keep that interaction cadence without putting the
                # bounded hardware wait back on the command-owner thread.
                self._measurement_stop.wait(0.100)
        except Exception as exc:
            print("SYNTH ultrasonic_worker_exception error=%r" % (exc,),
                  flush=True)
        finally:
            if self._sensor is not None:
                try:
                    self._sensor.close()
                except Exception as exc:
                    print("SYNTH ultrasonic_close_exception error=%r" % (exc,),
                          flush=True)
                self._sensor = None
            print("SYNTH ultrasonic_worker_stopped measurements=%d timeouts=%d "
                  "invalid=%d" %
                  (measurement_count, timeout_count, invalid_count), flush=True)

    def freq_to_midi(self, freq):
        return int(69 + 12 * math.log2(freq / 440.0))

    def _note_on(self, distance, reason, raw_distance=None):
        step = int((distance - self.min_distance) // 2)
        self.frequency = self.min_freq * (self.half_tone_ratio ** step)
        midi_note = self.freq_to_midi(self.frequency)
        now = time.monotonic()
        if (now - self._last_control_log >= 1.0 or
            (midi_note != self._last_control_midi and
             now - self._last_control_log >= 0.25)):
            print("SYNTH control raw_distance=%.2f control_distance=%.2f "
                  "step=%d midi=%d source=%s" %
                  (distance if raw_distance is None else raw_distance,
                   distance, step, midi_note, reason), flush=True)
            self._last_control_log = now
            self._last_control_midi = midi_note
        if midi_note == self.current_note:
            return
        if self.current_note is not None:
            self._note_off("note_change")
        result = self.fs.noteon(0, midi_note, 120)
        print("SYNTH note_on midi=%d distance_cm=%.2f instrument=%d "
              "source=%s return=%r" %
              (midi_note, distance, self.instrument, reason, result),
              flush=True)
        if result is None or result >= 0:
            self.current_note = midi_note

    def _note_off(self, reason):
        if self.current_note is None:
            return
        midi_note = self.current_note
        result = self.fs.noteoff(0, midi_note)
        print("SYNTH note_off midi=%d reason=%s return=%r" %
              (midi_note, reason, result), flush=True)
        self.current_note = None

    def update(self):
        with self._distance_lock:
            distance = self._distance
            latest_valid_distance = self._latest_valid_distance
            latest_valid_at = self._latest_valid_at

        self.in_range = self.min_distance <= distance <= self.max_distance
        if self.in_range:
            self.last_valid_distance = distance
        now = time.monotonic()
        physical_pressed = {
            index for index, pin in enumerate(self.generic_inputs)
            if GPIO.input(pin)}
        # Polling remains the fallback if RPi.GPIO debounce suppresses a very
        # short release edge; an explicit release still stops immediately.
        self._pressed_buttons.intersection_update(physical_pressed)
        physical_button = bool(physical_pressed)
        event_latched = now < self._button_latched_until
        self.button_held = (
            physical_button or bool(self._pressed_buttons) or event_latched)
        if not self.button_held:
            self._note_off("button_released")
            return

        if self.in_range:
            control_distance = distance
            source = "live_distance"
        elif latest_valid_at:
            # Preserve the original playable behavior: invalid/outlier samples
            # never replace or interrupt the last range-checked control value.
            control_distance = latest_valid_distance
            source = "held_last_valid"
        elif event_latched:
            control_distance = self.min_distance
            source = "button_latch_default"
        else:
            age = now - latest_valid_at if latest_valid_at else -1.0
            print("SYNTH note_skipped reason=no_valid_distance "
                  "raw_distance=%.2f last_valid_age_s=%.3f" %
                  (distance, age), flush=True)
            self._note_off("distance_invalid")
            return

        self._note_on(control_distance, source, raw_distance=distance)

    def buttonDown(self, buttonNumber):
        instruments = [86, 80, 71, 93, 19]
        button_index = buttonNumber % len(instruments)
        self.instrument = instruments[button_index]
        program_result = self.fs.program_select(
            0, self.sfid, 0, self.instrument)
        now = time.monotonic()
        with self._distance_lock:
            distance = self._distance
            latest_valid_distance = self._latest_valid_distance
            latest_valid_at = self._latest_valid_at
        distance_valid = self.min_distance <= distance <= self.max_distance
        control_distance = distance if distance_valid else latest_valid_distance
        if distance_valid:
            source = "generic_live_distance"
        elif latest_valid_at:
            source = "generic_last_valid"
        else:
            source = "generic_default_distance"
        valid_age = now - latest_valid_at if latest_valid_at else -1.0
        pin_level = GPIO.input(self.generic_inputs[button_index])
        self._pressed_buttons.add(button_index)
        self._button_latched_until = now + 0.30
        print("SYNTH generic index=%d instrument=%d pin=%d level=%d "
              "raw_distance=%.2f distance_valid=%s control_distance=%.2f "
              "last_valid_age_s=%.3f program_select_return=%r" %
              (button_index, self.instrument,
               self.generic_inputs[button_index], pin_level, distance,
               distance_valid, control_distance, valid_age, program_result),
              flush=True)
        self._note_on(control_distance, source, raw_distance=distance)

    def buttonUp(self, buttonNumber):
        button_index = buttonNumber % len(self.generic_inputs)
        self._pressed_buttons.discard(button_index)
        self._button_latched_until = 0.0
        print("SYNTH generic_release index=%d remaining=%d" %
              (button_index, len(self._pressed_buttons)), flush=True)
        if not self._pressed_buttons:
            self._note_off("button_released_event")
        return True

    def stop(self):
        cleanup_started = time.monotonic()
        print("SYNTH cleanup_begin uptime=%.6f worker_alive=%s note=%s" %
              (cleanup_started,
               self._measurement_thread is not None and
               self._measurement_thread.is_alive(), self.current_note),
              flush=True)
        self._measurement_stop.set()
        if self._measurement_thread is not None:
            self._measurement_thread.join(timeout=0.2)
            if self._measurement_thread.is_alive():
                print("SYNTH ultrasonic_worker_stop_timeout uptime=%.6f "
                      "wait_ms=200" % time.monotonic(), flush=True)
            else:
                print("SYNTH ultrasonic_worker_join_complete uptime=%.6f "
                      "duration_ms=%.3f" %
                      (time.monotonic(),
                       (time.monotonic() - cleanup_started) * 1000.0),
                      flush=True)
            self._measurement_thread = None

        if self.fs is None:
            self.is_playing = False
            return
        if self.current_note is not None:
            try:
                self._note_off("synth_stop")
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
        print("SYNTH cleanup_complete uptime=%.6f duration_ms=%.3f" %
              (time.monotonic(),
               (time.monotonic() - cleanup_started) * 1000.0), flush=True)
