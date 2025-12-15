#!/usr/bin/python
from SoundPlayer import SoundPlayerBase
import RPi.GPIO as GPIO

class MusicPlayer(SoundPlayerBase):

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)
        self.setList(path)

        self.playNext()

        # maybe we do the following in the base class!
        # GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(5), bouncetime=300)

    # play next song in current list
    def playNext(self):
        print("MusicPlayer playNext song")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileType < 0:
            self.currentFileType = 0
        else:
            self.currentFileType = (self.currentFileType + 1) % self.numberOfItemsInList

        print("play next: " + self.filelist[self.currentFileType])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileType])

    # play previous song in current list
    def playPrevious(self):
        print("MusicPlayer playPrevious song")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileType < 0:
            self.currentFileType = 0
        else:
            self.currentFileType = self.currentFileType - 1
            if self.currentFileType < 0:
                self.currentFileType = self.numberOfItemsInList - 1

        print("play prev: " + self.filelist[self.currentFileType])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.filelist[self.currentFileType])

    # select playlist with generic buttons
    def buttonDown(self, buttonNumber):
        print("MusicPlayer pressed generic button in online player " + str(buttonNumber))
        # self.currentFileType = 1
        # print("play: " + self.filelist[self.currentSong])
        # self.player.stop() # TODO: check if necessary
        # self.player.play_song(self.filelist[buttonNumber])

        songNumber = buttonNumber % len(self.filelist)
        # self.setList(f"./Sounds/Music/0{songNumber}/*.mp3")
        # self.playNext()
        self.playSong(self.filelist[songNumber])