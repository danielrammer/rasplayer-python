#!/usr/bin/python

from SoundPlayer import SoundPlayerBase
from enum import IntEnum
import glob
import pygame

# Ensure mixer initialized with a larger buffer to reduce ALSA underrun occurrences.
def ensure_mixer_initialized(frequency=44100, size=-16, channels=2, buffer=4096):
    """Initialize pygame mixer only once with the given parameters.

    Larger buffer sizes (e.g., 4096 or 8192) reduce the chance of ALSA underruns on Raspberry Pi.
    Call this before loading/playing sounds.
    """
    if not pygame.mixer.get_init():
        try:
            # pre_init should be called before init to set buffer/format
            pygame.mixer.pre_init(frequency, size, channels, buffer=buffer)
            pygame.mixer.init()
        except Exception as e:
            print(f"Warning: could not initialize mixer: {e}")

NUMBER_OF_SAMPLE_SETS = 5

class SamplePlayer(SoundPlayerBase):
    instrumentRootPath = "./Sounds/Instruments"
    animalRootPath = "./Sounds/Animals"

    activeSoundFileRoot = ""

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)
        self.activeSoundFileRoot = path
        self.currentSampleSet = 0
        print("SamplePlayer set list: " + f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")
        self.setList(f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")

        # Initialize Pygame mixer (safe single initialization with larger buffer)
        ensure_mixer_initialized()
        # preload all samples for a given list
        self.samples = [pygame.mixer.Sound(file) for file in self.filelist]
        # for index, sample in enumerate(self.samples):
        #     print(f"Sample {index}: {sample}")

    # def preload_samples():
    #     self.samples = [pygame.mixer.Sound(file) for file in self.filelist]

    # select next button mapping for generic buttons
    def playNext(self):
        print("SamplePlayer playNext - next set")
        self.currentSampleSet = (self.currentSampleSet + 1) % NUMBER_OF_SAMPLE_SETS

        print("SamplePlayer set list: " + f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")
        self.setList(f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")
        # self.samples = []
        # Rebuild sample list without reinitializing the mixer
        self.samples = [pygame.mixer.Sound(file) for file in self.filelist]

    # select previous button mapping for generic buttons
    def playPrevious(self):
        print("SamplePlayer playPrevious")
        self.currentSampleSet = self.currentSampleSet - 1
        if self.currentSampleSet < 0:
            self.currentSampleSet = NUMBER_OF_SAMPLE_SETS - 1

        print("SamplePlayer set list: " + f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")
        self.setList(f"{self.activeSoundFileRoot}/{self.currentSampleSet}/*.mp3")
        # rebuild samples (don't re-init mixer)
        self.samples = [pygame.mixer.Sound(file) for file in self.filelist]
        
    # fire sound file
    def buttonDown(self, buttonNumber):
        print("SamplePlayer pressed generic button in online player " + str(buttonNumber))
        self.currentFileNum = 1
        # print("list length: " + str(len(self.filelist)))
        self.player.stop() # TODO: check if necessary



        if (len(self.filelist) > 0):
            soundNumber = buttonNumber % len(self.filelist)
            print("play: " + self.filelist[soundNumber])
            # self.player.play_song(self.filelist[buttonNumber])

            # Load and play an MP3 file
            # pygame.mixer.music.load(self.filelist[buttonNumber])
            # pygame.mixer.music.play()
            self.samples[soundNumber].play()
        else:
            print("No sound files loaded!")
        