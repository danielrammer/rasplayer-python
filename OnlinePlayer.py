#!/usr/bin/python
import time
import vlc
from SoundPlayer import SoundPlayerBase

class OnlinePlayer(SoundPlayerBase):

    def __init__(self, vlcInstance, player, path):
        SoundPlayerBase.__init__(self, vlcInstance, player, path)

        # GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(5), bouncetime=300)
        
        self._open_started = None
        self._last_state = None
        self._failure_reported = False
        self.playNext()


    radios = {
        0: "http://mp3channels.webradio.antenne.de/rockantenne",    # Rockantenne
        1: "http://mp3channels.webradio.antenne.de/80er-kulthits",  # 80er-Kulthits
        2: "http://mp3channels.webradio.antenne.de/workout-hits",   # Workout Hits
        3: "http://mp3channels.webradio.antenne.de/chillout",       # Chillout
        4: "http://mp3channels.webradio.antenne.de/hitmix",         # hitmix
        #5: "http://mp3channels.webradio.antenne.de/80er-kulthits",   # /80er-kulthits
        #6: "http://live-icy.gss.dr.dk:8000/A/A25H.mp3"              # DR P5 (Oldies)
    }

    currentRadio = -1
    numberOfRadios = len(radios)

    def buttonDown(self, buttonNumber):
        print("OnlinePlayer pressed generic button in online player " + str(buttonNumber))
        if buttonNumber not in self.radios:
            print("OnlinePlayer station switch ignored: invalid channel %s" %
                  buttonNumber, flush=True)
            return False
        self.currentRadio = buttonNumber
        print("OnlinePlayer play " + self.radios[self.currentRadio])
        # self.player.stop() # TODO: check if necessary

        return self._open(self.radios[self.currentRadio])

    def _open(self, url):
        self._open_started = time.monotonic()
        self._last_state = None
        self._failure_reported = False
        print("ONLINE open_begin uptime=%.6f url=%s" %
              (self._open_started, url), flush=True)
        media = self.vlcInstance.media_new(url)
        media.add_option(":network-caching=1000")
        media.add_option(":http-reconnect")
        self.player.set_media(media)
        result = self.player.play()
        print("ONLINE play_return uptime=%.6f result=%s call_ms=%.3f" %
              (time.monotonic(), result,
               (time.monotonic() - self._open_started) * 1000.0), flush=True)
        self.is_playing = result != -1
        return self.is_playing

    def playNext(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentRadio < 0:
            self.currentRadio = 0
        else:
            self.currentRadio = (self.currentRadio + 1) % self.numberOfRadios

        print("play next: " + self.radios[self.currentRadio])
        # self.player.stop() # TODO: check if necessary

        return self._open(self.radios[self.currentRadio])

    def playPrevious(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentRadio < 0:
            self.currentRadio = 0
        else:
            self.currentRadio = self.currentRadio - 1
            if self.currentRadio < 0:
                self.currentRadio = self.numberOfRadios - 1

        print("play next: " + self.radios[self.currentRadio])
        # self.player.stop() # TODO: check if necessary
        return self._open(self.radios[self.currentRadio])

    def update(self):
        if self._open_started is None:
            return
        state = self.player.get_state()
        now = time.monotonic()
        if state != self._last_state:
            print("ONLINE state uptime=%.6f elapsed_ms=%.3f state=%s" %
                  (now, (now - self._open_started) * 1000.0, state),
                  flush=True)
            self._last_state = state
        if state == vlc.State.Playing:
            self.is_playing = True
            return
        if state in (vlc.State.Error, vlc.State.Ended, vlc.State.Stopped):
            if not self._failure_reported:
                print("ONLINE failure uptime=%.6f elapsed_ms=%.3f state=%s" %
                      (now, (now - self._open_started) * 1000.0, state),
                      flush=True)
                self._failure_reported = True
            self.is_playing = False
        elif now - self._open_started >= 8.0 and not self._failure_reported:
            print("ONLINE timeout uptime=%.6f elapsed_ms=%.3f state=%s" %
                  (now, (now - self._open_started) * 1000.0, state),
                  flush=True)
            self._failure_reported = True
            self.is_playing = False
