#!/usr/bin/python

from SoundPlayer import SoundPlayerBase
from enum import IntEnum
import glob

import pygame

NUMBER_OF_SAMPLE_SETS = 3

class SamplePlayer(SoundPlayerBase):
    currentSampleSet = 0

    instrumentRootPath = "./Sounds/Instruments"
    animalRootPath = "./Sounds/Animals"

    activeSoundFileRoot = ""

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)
        self.activeSoundFileRoot = path
        print("SamplePlayer set list: " + f"{self.activeSoundFileRoot}/*.mp3")
        self.setList(f"{self.activeSoundFileRoot}/*.mp3")

        # Initialize Pygame mixer
        pygame.mixer.init()
        # preload all samples for a given list
        self.samples = [pygame.mixer.Sound(file) for file in self.filelist]
        # for index, sample in enumerate(self.samples):
        #     print(f"Sample {index}: {sample}")

    # select next button mapping for generic buttons
    def playNext(self):
        print("SamplePlayer playNext - next set")
        self.currentSampleSet = (self.currentSampleSet + 1) % NUMBER_OF_SAMPLE_SETS


    # select previous button mapping for generic buttons
    def playPrevious(self):
        print("SamplePlayer playPrevious")
        self.currentSampleSet = self.currentSampleSet - 1
        if self.currentSampleSet < 0:
            self.currentSampleSet = NUMBER_OF_SAMPLE_SETS - 1
        self.setList(f"{self.activeSoundFileRoot}/*.mp3")

    # fire sound file
    def buttonDown(self, buttonNumber):
        print("SamplePlayer pressed generic button in online player " + str(buttonNumber))
        self.currentFileType = 1
        # print("list length: " + str(len(self.filelist)))
        self.player.stop() # TODO: check if necessary
        print("play: " + self.filelist[buttonNumber])
        # self.player.play_song(self.filelist[buttonNumber])

        # Load and play an MP3 file
        # pygame.mixer.music.load(self.filelist[buttonNumber])
        # pygame.mixer.music.play()
        self.samples[buttonNumber].play()