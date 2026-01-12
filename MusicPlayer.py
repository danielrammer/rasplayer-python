#!/usr/bin/python
from SoundPlayer import SoundPlayerBase
from time import sleep
import RPi.GPIO as GPIO
from mpyg321.consts import MPyg321Events
from mpyg321.MPyg123Player import PlayerStatus
from mpyg321.MPyg123Player import MPyg123Player

class MusicPlayer(SoundPlayerBase):


    currentSong = None
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

        player.subscribe_event(MPyg321Events.MUSIC_END, self.on_song_end)

    # callback when song ends
    def on_song_end(self, context):
        # IMPORTANT: stop first to break the event loop condition
        # try:
        #     self.player.stop()
        # except Exception:
        #     pass

        
        
        print("MusicPlayer on_song_end - playing next")

        if not self.is_playing:
            print("MusicPlayer on_song_end - not playing")
            return

        print("PlayerStatus.PLAYING " + str(PlayerStatus.PLAYING) + " STATUS " + str(self.player.status))

        # Start next track AFTER stopping
        if self.player.status != PlayerStatus.PLAYING:
            print("PlayerStatus.PLAYING " + str(PlayerStatus.PLAYING))
            print("Status "+ str(self.player.status) + " - playing next")
            self.playNext()

    # play next song in current list
    def playNext(self):
        print("MusicPlayer playNext song")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = (self.currentFileNum + 1) % self.numberOfItemsInList

        self.currentSong = self.filelist[self.currentFileNum]
        print("play next: " + self.currentSong)
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.currentSong)
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
        pass
        # if not self.player.playing():
        #     if self.is_playing: # song ended
        #         self.playNext()