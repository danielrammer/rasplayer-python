#!/usr/bin/python

from SoundPlayer import SoundPlayerBase
from enum import IntEnum

NUMBER_OF_SAMPLE_SETS = 3

class SamplePlayer(SoundPlayerBase):
    currentSampleSet = 0

    instrumentRootPath = "./Sounds/Instruments"
    animalRootPath = "./Sounds/Animals"

    activeSoundFileRoot = ""

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)
        self.activeSoundFileRoot = path

    # select next button mapping for generic buttons
    def playNext(self):
        print("SamplePlayer playNext - next set")
        self.currentSampleSet = (self.currentSampleSet + 1) % NUMBER_OF_SAMPLE_SETS
        self.setList(f"{self.activeSoundFileRoot}/*.mp3")

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
        # print("play: " + self.filelist[self.currentSong])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.radios[buttonNumber])