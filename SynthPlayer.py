import RPi.GPIO as GPIO
import pyaudio
import numpy as np


class SynthPlayer:
    def __init__(self, vlcInstance, player, path, get_distance_func):
        self.is_playing = True  # Always playing for synth
        self.frequency = 440  # Default A4
        self.waveform = 0  # 0: sine, 1: square, 2: saw, 3: triangle
        self.get_distance = get_distance_func
        self.button_held = False  # Track if any generic button is held
        self.in_range = False  # Track if distance is within frequency mapping range

        # Frequency mapping parameters
        self.min_freq = 100
        self.max_freq = 1000
        self.min_distance = 5  # Minimum distance in cm for frequency mapping
        self.max_distance = 17  # Maximum distance in cm for frequency mapping
        self.whole_tone_ratio = 2 ** (1 / 6)  # Ratio for one whole tone (2 half-tones)

        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paFloat32,
                                  channels=1,
                                  rate=44100,
                                  output=True,
                                  stream_callback=self.callback)
        self.stream.start_stream()

        # Setup generic inputs for waveform selection
        self.generic_inputs = [11, 5, 6, 19, 16]  # BCM pins
        for pin in self.generic_inputs:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.add_event_detect(pin, GPIO.RISING, callback=self.change_waveform, bouncetime=200)

    def change_waveform(self, channel):
        index = self.generic_inputs.index(channel)
        self.waveform = index % 4  # Cycle through 4 waveforms
        print(f"Waveform changed to {self.waveform}")

    def update(self):
        # Update frequency based on distance
        distance = self.get_distance()
        step = 0  # Default
        if distance > 0:
            if distance < self.min_distance:
                step = 0
            elif distance > self.max_distance:
                step = 5  # 5 half-tones for the 10cm range (5 steps of 2cm each)
            else:
                step = int((distance - self.min_distance) // 2)
            self.frequency = self.min_freq * (self.whole_tone_ratio ** step)
            self.in_range = True  # Always play when distance > 0
        else:
            self.frequency = 220  # Default if no distance
            self.in_range = False  # Don't play if no valid distance

        print(f"Distance: {distance:.2f} cm, Step: {step}, Frequency: {self.frequency:.2f} Hz, In range: {self.in_range}")
        # Check if any generic button is held down
        self.button_held = any(GPIO.input(pin) for pin in self.generic_inputs)

    def callback(self, in_data, frame_count, time_info, status):
        if not (self.button_held and self.in_range):
            data = np.zeros(frame_count, dtype=np.float32)
        else:
            t = np.linspace(0, frame_count / 44100, frame_count, False)
            if self.waveform == 0:  # Sine
                data = np.sin(2 * np.pi * self.frequency * t)
            elif self.waveform == 1:  # Square
                data = np.sign(np.sin(2 * np.pi * self.frequency * t))
            elif self.waveform == 2:  # Sawtooth
                data = 2 * (t * self.frequency - np.floor(t * self.frequency + 0.5))
            elif self.waveform == 3:  # Triangle
                data = 2 * np.abs(2 * (t * self.frequency - np.floor(t * self.frequency + 0.5))) - 1
            else:
                data = np.random.uniform(-1, 1, frame_count)  # Noise
        return (data.astype(np.float32), pyaudio.paContinue)

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        self.is_playing = False
