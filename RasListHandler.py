#!/usr/bin/python
import glob
import RPi.GPIO as GPIO
from enum import IntEnum
from mpyg321.MPyg123Player import MPyg123Player # or MPyg321Player if you installed mpg321

class RasListHandler:

    player = None
    filelist = ""
    numberOfSongs = 0
    currentSong = 0

    def __init__(self, player, path):
        self.player = player
        self.currentSong = -1
        self.filelist = glob.glob(path)
        self.filelist.sort()
        self.numberOfSongs = len(self.filelist)
        print("selected list: " + str(self.filelist))

        GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)

    GPIO.setmode(GPIO.BCM)

    # TODO: set GPIO
    class GenericInput(IntEnum):
        IN_1 = 27#23
        IN_2 = 22#24
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

    def playSongExt(self, test):
        print("play ext")
        self.player.play_song(self.filelist[1])

    for i in inputs:
        GPIO.setup(i, GPIO.IN)
        GPIO.setup(i, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def buttonDown(self, soundNumber):
        print("pressed generic button " + str(soundNumber))
        self.currentSong = 1
        # print("play: " + self.filelist[self.currentSong])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[soundNumber])