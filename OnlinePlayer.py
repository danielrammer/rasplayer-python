#!/usr/bin/python
from SoundPlayer import SoundPlayerBase
import RPi.GPIO as GPIO

class OnlinePlayer(SoundPlayerBase):

    def __init__(self, player, path):
        SoundPlayerBase.__init__(self, player, path)

        # GPIO.add_event_detect(self.GenericInput.IN_1, GPIO.RISING,  callback=lambda x : self.buttonDown(1), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_2, GPIO.RISING,  callback=lambda x : self.buttonDown(2), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_3, GPIO.RISING,  callback=lambda x : self.buttonDown(3), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_4, GPIO.RISING,  callback=lambda x : self.buttonDown(4), bouncetime=300)
        # GPIO.add_event_detect(self.GenericInput.IN_5, GPIO.RISING,  callback=lambda x : self.buttonDown(5), bouncetime=300)

    radios = {
        0: "http://mp3channels.webradio.antenne.de/rockantenne",    # Rockantenne
        1: "http://mp3channels.webradio.antenne.de/80er-kulthits",  # 80er-Kulthits
        2: "http://live-radio01.mediahubaustralia.com/DJDW/mp3",    # ABC Double J
        3: "http://live-radio01.mediahubaustralia.com/JAZW/mp3",    # ABC Jazz
        4: "http://live-radio02.mediahubaustralia.com/2FMW/mp3"#,    # ABC Classic
        #5: "http://mp3channels.webradio.antenne.de/workout-hits",   # Workout Hits
        #6: "http://live-icy.gss.dr.dk:8000/A/A25H.mp3"              # DR P5 (Oldies)
    }

    currentRatio = -1
    numberOfRadios = len(radios)

    def buttonDown(self, buttonNumber):
        print("OnlinePlayer pressed generic button in online player " + str(buttonNumber))
        self.currentRatio = buttonNumber
        print("OnlinePlayer play" + self.radios[self.currentRatio])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.radios[self.currentRatio])
        self.is_playing = True

    def playNext(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentRatio < 0:
            self.currentRatio = 0
        else:
            self.currentRatio = (self.currentRatio + 1) % self.numberOfRadios

        print("play next: " + self.radios[self.currentRatio])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.radios[self.currentRatio])

    def playPrevious(self):
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentRatio < 0:
            self.currentRatio = 0
        else:
            self.currentRatio = self.currentRatio - 1
            if self.currentRatio < 0:
                self.currentRatio = self.numberOfRadios - 1

        print("play next: " + self.radios[self.currentRatio])
        self.player.stop() # TODO: check if necessary
        self.player.play_song(self.radios[self.currentRatio])