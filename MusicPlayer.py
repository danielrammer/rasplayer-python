#!/usr/bin/python
from SoundPlayer import SoundPlayerBase
from time import sleep
import RPi.GPIO as GPIO

class MusicPlayer(SoundPlayerBase):
    currentSong = None
    def __init__(self, vlcInstance, player, path):
        SoundPlayerBase.__init__(self, vlcInstance, player, path)
        print("MusicPlayer initialized with path: " + path)
        # self.setList(path)

        import queue
        self._actions = queue.Queue()

        self.player.stop()
        self.setList("./Sounds/Music/0" + str(1) + "/*.mp3")

        # maybe we do the following in the base class!
        # Generic GPIO callbacks are registered by RasPlayer's dispatcher.

        self._attach_events()

        sleep(1)
        self.playSongNumber(0)


    def _attach_events(self):
        import vlc
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

        self._events_attached = True

    def stop(self):
        """Detach this instance's VLC callback before the shared player is reused."""
        if getattr(self, "_events_attached", False):
            try:
                import vlc
                self.player.event_manager().event_detach(
                    vlc.EventType.MediaPlayerEndReached)
            except Exception as exc:
                print("MusicPlayer event cleanup failed: %s" % exc, flush=True)
            self._events_attached = False
        try:
            self.player.stop()
        except Exception:
            pass
        self.is_playing = False

    # callback when song ends
    def _on_song_end(self, event):
        print("Song ended")
        if SoundPlayerBase.input_dispatcher is not None:
            SoundPlayerBase.input_dispatcher("automatic_next", None)
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

    def navigate(self, offset):
        """Apply a coalesced navigation offset with one VLC open."""
        if not self.filelist:
            return False
        start = self.currentFileNum if self.currentFileNum >= 0 else 0
        self.currentFileNum = (start + offset) % self.numberOfItemsInList
        print("MUSIC navigate offset=%d from=%d to=%d" %
              (offset, start, self.currentFileNum), flush=True)
        self.playSongNumber(self.currentFileNum)
        return True

    def playSongNumber(self, number):
        print("MusicPlayer playSongNumber: " + str(number))
        if number < 0 or number >= self.numberOfItemsInList:
            print("MusicPlayer playSongNumber: number out of range, resetting to 0")
            number = 0
            
        self.currentFileNum = number
        self.currentSong = self.filelist[self.currentFileNum]
        print("play song: " + self.currentSong)

        media = self.vlcInstance.media_new(self.currentSong)
        self.player.set_media(media)
        self.player.play()

        self.is_playing = True

    # select playlist with generic buttons
    def buttonDown(self, buttonNumber):
        print("MusicPlayer pressed generic button " + str(buttonNumber))
        self.player.stop()
        self.setList("./Sounds/Music/0" + str(buttonNumber) + "/*.mp3")

        if not self.filelist:
            print("MusicPlayer playlist switch ignored: empty playlist %d" %
                  buttonNumber, flush=True)
            return False

        self.currentFileNum = 0
        print("Current file num set to 0 == " + str(self.currentFileNum))

        self.playSong(self.filelist[self.currentFileNum])
        return True

    def update(self):
        super().update()
        # self.autoPlayNext()


    # def autoPlayNext(self):
    #     action = self._actions.get()
    #     action()
