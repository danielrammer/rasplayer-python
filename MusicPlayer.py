#!/usr/bin/python
from asyncio import events
from SoundPlayer import SoundPlayerBase
from time import sleep
import RPi.GPIO as GPIO
import vlc
import queue
import threading

class MusicPlayer(SoundPlayerBase):
    currentSong = None
    _events_attached = False

    def __init__(self, vlcInstance, player, path):
        SoundPlayerBase.__init__(self, vlcInstance, player, path)
        print("MusicPlayer initialized with path: " + path)
        # self.setList(path)

        self._actions = queue.Queue()
        # self.playNext()

        # maybe we do the following in the base class!
        self.removeAllGenericGPIOEvents()
        GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(0), bouncetime=400)
        GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=400)
        GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=400)
        GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=400)
        GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=400)

        self._attach_events()


    def _attach_events(self):
        # ensure any previous end events are detached, then attach for this instance
        events = self.player.event_manager()
        try:
            events.event_detach(vlc.EventType.MediaPlayerEndReached)
        except Exception:
            # event_detach may raise if nothing was attached; ignore
            pass

        events.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_song_end
        )

        MusicPlayer._events_attached = True

    # callback when song ends
    def _on_song_end(self, event):
        print("Song ended")
        threading.Thread(target=self.playNext, daemon=True).start()
         #self._actions.put(self.playNext)

    # play next song in current list
    def playNext(self):
        print("MusicPlayer playNext song")
        # play first if list was newly selected
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            print("MusicPlayer currentFileNum before increment: " + str(self.currentFileNum))
            self.currentFileNum = (self.currentFileNum + 1) % self.numberOfItemsInList

        print("list content: " + str(self.filelist) + " with length " + str(len(self.filelist)))

        self.currentSong = self.filelist[self.currentFileNum]
        print("play next: " + self.currentSong)

        media = self.vlcInstance.media_new(self.currentSong)
        self.player.set_media(media)
        self.player.play()

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

        self.currentSong = self.filelist[self.currentFileNum]
        print("play prev: " + self.currentSong)

        media = self.vlcInstance.media_new(self.currentSong)
        self.player.set_media(media)
        self.player.play()

        self.is_playing = True

    # select playlist with generic buttons
    def buttonDown(self, buttonNumber):
        print("MusicPlayer pressed generic button " + str(buttonNumber))
        self.player.stop()
        self.setList("./Sounds/Music/0" + str(buttonNumber) + "/*.mp3")

        self.currentFileNum = 0
        print("Current file num set to 0 == " + str(self.currentFileNum))

        self.playSong(self.filelist[self.currentFileNum])

    def update(self):
        super().update()
        # self.autoPlayNext()


    # def autoPlayNext(self):
    #     action = self._actions.get()
    #     action()