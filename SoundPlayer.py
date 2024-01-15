#!/usr/bin/python
import glob
import RPi.GPIO as GPIO
from enum import IntEnum
from mpyg321.MPyg123Player import MPyg123Player # or MPyg321Player if you installed mpg321

class SoundPlayer:

    player = None
    filelist = ""
    numberOfSongsInList = 0
    currentFileType = 0 # this is the type (e.g. pig sound)
    currentFile = 0     # this is the actual sound file (e.g. pig sound #2)


    class GenericInput(IntEnum):
        IN_1 = 23
        IN_2 = 24
        IN_3 = 25
        IN_4 = 12
        IN_5 = 16
        IN_6 = 5
        IN_7 = 6

    inputs = [GenericInput.IN_1, 
              GenericInput.IN_2,
              GenericInput.IN_3,
              GenericInput.IN_4,
              GenericInput.IN_5,
              GenericInput.IN_6,
              GenericInput.IN_7]

    def __init__(self, player, path):
        print("Instantiated ModeHandler")
        self.player = player
        self.setList(path)
        # GPIO setup - use logical numbering not hw numbering
        GPIO.setmode(GPIO.BCM)
        # setup input mapping
        for i in self.inputs:
                GPIO.setup(i, GPIO.IN)
                GPIO.setup(i, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


        # GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)

    # TODO: make 2D array to allow more sounds per type
    def setList(self, path):
        self.currentFileType = -1
        self.filelist = glob.glob(path)
        self.filelist.sort()
        self.numberOfSongsInList = len(self.filelist)
        print("selected list in mgr: " + str(self.filelist))


    def playSong(self, path):
        print("play song: " + str(path))
        self.player.play_song(path)

    def playNextSong(self):
        self.currentFileType = (self.currentFileType + 1) % self.numberOfSongsInList
        print("play next: " + self.filelist[self.currentFileType])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileType])

    def playPreviousSong(self):
        self.currentFileType = self.currentFileType - 1
        if self.currentFileType < 0:
            self.currentFileType = self.numberOfSongsInList - 1
        print("play prev: " + self.filelist[self.currentFileType])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileType])

    def buttonDown(self, soundNumber):
        print("pressed generic button " + str(soundNumber))
        self.currentFileType = 1
        # print("play: " + self.filelist[self.currentSong])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[soundNumber])