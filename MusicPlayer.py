#!/usr/bin/python
from SoundPlayer import SoundPlayerBase
from time import sleep
import RPi.GPIO as GPIO

class MusicPlayer(SoundPlayerBase):

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)
        print("MusicPlayer initialized with path: " + path)
        self.setList(path)

        # self.playNext()

        # maybe we do the following in the base class!
        self.removeAllGenericGPIOEvents()
        GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(0), bouncetime=300)
        GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)
        GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=300)
        GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=300)
        GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=300)

    # play next song in current list
    def playNext(self):
        print("MusicPlayer playNext song")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = (self.currentFileNum + 1) % self.numberOfItemsInList

        print("play next: " + self.filelist[self.currentFileNum])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileNum])
        self.is_playing = True

    # play previous song in current list
    def playPrevious(self):
        print("MusicPlayer playPrevious song")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = self.currentFileNum - 1
            if self.currentFileNum < 0:
                self.currentFileNum = self.numberOfItemsInList - 1

        print("play prev: " + self.filelist[self.currentFileNum])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileNum])
        self.is_playing = True

    # select playlist with generic buttons
    def buttonDown(self, buttonNumber):
        print("MusicPlayer pressed generic button " + str(buttonNumber))
        self.player.stop()
        self.setList("./Sounds/Music/0" + str(buttonNumber) + "/*.mp3")

        self.currentFileNum = 0

        self.playSong(self.filelist[self.currentFileNum])
        self.is_playing = True

    def update(self):
        super().update()
        self.autoPlayNext()

    def autoPlayNext(self):
        if not self.player.playing_now():
            if self.is_playing: # song ended
                self.playNext()