import RPi.GPIO as GPIO
import pyaudio
import numpy as np


class SynthPlayer:
    def __init__(self, vlcInstance, player, path, get_distance_func):
        self.is_playing = True  # Always playing for synth
        self.frequency = 440  # Default A4
        self.waveform = 0  # 0: sine, 1: square, 2: saw, 3: triangle
        self.get_distance = get_distance_func

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
        if distance > 0:
            self.frequency = np.clip(200 + (distance - 10) * 20, 100, 2000)  # Map 10cm=200Hz to 100cm=2000Hz
        else:
            self.frequency = 440  # Default if no distance

    def callback(self, in_data, frame_count, time_info, status):
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
