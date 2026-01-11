#!/usr/bin/python
import glob
import RPi.GPIO as GPIO
from enum import IntEnum
from mpyg321.MPyg123Player import MPyg123Player # or MPyg321Player if you installed mpg321

class SoundPlayerBase:
    player = None
    is_playing = False
    filelist = ""
    numberOfItemsInList = 0
    currentFileNum = -1 # TODO: this is the type (e.g. pig sound)
    # currentFile = 0     # TODO: this is the actual sound file (e.g. pig sound #2)

    # input mapping to GPIO BCM
    class GenericInput(IntEnum):
        IN_1 = 11
        IN_2 = 5
        IN_3 = 6
        IN_4 = 19
        IN_5 = 16

    inputs = [GenericInput.IN_1, 
              GenericInput.IN_2,
              GenericInput.IN_3,
              GenericInput.IN_4,
              GenericInput.IN_5]

    def __init__(self, player, path):
        # print("SoundPlayerBase Instantiated ModeHandler")
        print("SoundPlayerBase initialized with path: " + path)
        self.player = player
        self.is_playing = False
        # self.setList(path)
        # GPIO setup - use logical numbering not hw numbering
        GPIO.setmode(GPIO.BCM)
        # setup input mapping
        for i in self.inputs:
            GPIO.setup(i, GPIO.IN)
            GPIO.setup(i, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            print("setup input: " + str(i) + " to IN")

        self.removeAllGenericGPIOEvents()
        GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(0), bouncetime=250)
        GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=250)
        GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=250)
        GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=250)
        GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=250)

        # GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)
        
        self.pausePlayer()

    def removeAllGenericGPIOEvents(self):
        print("removing all generic GPIO events")
        GPIO.remove_event_detect(self.GenericInput.IN_1)
        GPIO.remove_event_detect(self.GenericInput.IN_2)
        GPIO.remove_event_detect(self.GenericInput.IN_3)
        GPIO.remove_event_detect(self.GenericInput.IN_4)
        GPIO.remove_event_detect(self.GenericInput.IN_5)

    # TODO: make 2D array to allow more sounds per type
    def setList(self, path):
        self.currentFileNum = 0
        self.filelist = glob.glob(path)
        self.filelist.sort()
        self.numberOfItemsInList = len(self.filelist)
        print("selected list in mgr: " + str(self.filelist))


    def playSong(self, path):
        print("play song: " + str(path))
        self.player.play_song(path)
        self.is_playing = True

    def playNext(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = (self.currentFileNum + 1) % self.numberOfItemsInList

        print("play next: " + self.filelist[self.currentFileNum])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileNum])
        self.is_playing = True

    def playPrevious(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = self.currentFileNum - 1
            if self.currentFileNum < 0:
                self.currentFileNum = self.numberOfItemsInList - 1

        print("play prev: " + self.filelist[self.currentFileNum])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileNum])
        self.is_playing = True

    def playPausePlayer(self): 
        if self.is_playing:
            self.player.pause()
            self.is_playing = False

            print("SoundPlayer: pausing player at currentNum " + str(self.currentFileNum))
        else:
            print("SoundPlayer: resuming currentNum " + str(self.currentFileNum))
            if (self.currentFileNum < 0):
                self.currentFileNum = 0
                print("play first song: " + self.filelist[self.currentFileNum])
                self.player.play_song(self.filelist[self.currentFileNum])
            else:
                self.player.resume()
        
            self.is_playing = True
            print("SoundPlayer: resuming player")

    def pausePlayer(self):
        self.is_playing = False
        self.player.pause()

    def buttonDown(self, buttonNumber):
        print("pressed generic button " + str(buttonNumber))
        self.currentFileNum = 1
        print("play: " + self.filelist[self.currentFileNum])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[buttonNumber])

    def on_playback_started(self):
        print("Playback started")
        self.is_playing = True

    def on_playback_finished(self):
        print("Playback finished")
        self.is_playing = False

    def is_playing_now(self):
        return self.is_playing
    
    def update(self):
        pass