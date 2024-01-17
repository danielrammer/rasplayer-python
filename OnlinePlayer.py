#!/usr/bin/python
from SoundPlayer import SoundPlayer

class OnlinePlayer(SoundPlayer):

    radios = {
        0: "http://mp3channels.webradio.antenne.de/rockantenne",    # Rockantenne
        1: "http://mp3channels.webradio.antenne.de/80er-kulthits",  # 80er-Kulthits
        2: "http://live-radio01.mediahubaustralia.com/DJDW/mp3",    # ABC Double J
        3: "http://live-radio01.mediahubaustralia.com/JAZW/mp3",    # ABC Jazz
        4: "http://live-radio02.mediahubaustralia.com/2FMW/mp3",    # ABC Classic
        5: "http://mp3channels.webradio.antenne.de/workout-hits",   # Workout Hits
        6: "http://live-icy.gss.dr.dk:8000/A/A25H.mp3"              # DR P5 (Oldies)
    }

    currentRatio = -1
    numberOfRadios = len(radios)

    def buttonDown(self, buttonNumber):
        print("pressed generic button in online player " + str(buttonNumber))
        self.currentFileType = 1
        # print("play: " + self.filelist[self.currentSong])
        # self.player.stop() # TODO: check if necessary
        self.player.play_song(self.radios[buttonNumber])

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