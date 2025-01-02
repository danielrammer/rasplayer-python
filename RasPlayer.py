#!/usr/bin/python
import glob
import subprocess
import RPi.GPIO as GPIO
from time import sleep
from enum import IntEnum
from mpyg321.MPyg123Player import MPyg123Player # or MPyg321Player if you installed mpg321
import signal
import sys

from SoundPlayer import SoundPlayerBase
from MusicPlayer import MusicPlayer
from OnlinePlayer import OnlinePlayer
from SamplePlayer import SamplePlayer

## -------- HOW TO RUN THAT STUFF --------
# RUN: xvfb-run python RasPlayer.py
# set volume
# amixer sset 'Master' 50%
# ----------------------------------------

def cleanup_and_exit(signum, frame):
    print("Cleaning up GPIO and exiting.")
    GPIO.cleanup()  # Cleanup GPIO
    sys.exit(0)  # Exit the script

# Setup signal handler for SIGINT (Ctrl+C) and SIGTERM
signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)



GPIO.setmode(GPIO.BCM)      # Set's GPIO pins to BCM (logic) GPIO numbering

# -------- types --------
class PlayerMode(IntEnum):
    MUSIC = 0
    ANIMALS = 1
    INSTRUMENT = 2
    ONLINE = 3
    NONE = 4

# these inputs are global - work for all modes
# maybe fwd and prv are not available for all
class Input(IntEnum):
    INPUT_PLAY_PAUSE = 4
    INPUT_FWD = 17
    INPUT_PRV = 27
    # INPUT_MODE_CHG = 27 # will be wire (banana)
    INPUT_VOL_UP = 22
    INPUT_VOL_DOWN = 23
    INPUT_MUSIC_MODE = 24
    INPUT_ONLINE_MODE = 10
    INPUT_ANIMAL_MODE = 9
    INPUT_INSTRUMENT_MODE = 25

    NONE = 1337
mpgPlayer = MPyg123Player()
filelist = ""
currentSong = 0
currentVolume = 80
playerMode = PlayerMode.MUSIC

soundPlayer = SamplePlayer(mpgPlayer, "./Sounds/Instruments")#MusicPlayer(mpgPlayer, "./Sounds/Music/02/*.mp3") # OnlinePlayer(mpgPlayer, "") 

GPIO.setup(Input.INPUT_FWD, GPIO.IN)
GPIO.setup(Input.INPUT_PRV, GPIO.IN)
GPIO.setup(Input.INPUT_PLAY_PAUSE, GPIO.IN)
# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN)         # TODO: will be replaced by defined banana
# GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN)
# GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN)
# GPIO.setup(Input.INPUT_MUSIC_MODE, GPIO.IN)       # TODO: banana
# GPIO.setup(Input.INPUT_ANIMAL_MODE, GPIO.IN)      # TODO: banana
# GPIO.setup(Input.INPUT_INSTRUMENT_MODE, GPIO.IN)  # TODO: banana
# GPIO.setup(Input.INPUT_ONLINE_MODE, GPIO.IN)      # TODO: banana

# -------- function definitions --------

# other control functions
def setVolume(vol):
    print("set volume to " + str(vol))
    # subprocess.call(["amixer", "-D", "default", "sset", "Master", str(vol)+"%"], stdout=subprocess.DEVNULL)
    command  = ['amixer', '-c', '0', 'sset', 'PCM',  str(vol)+'%']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def volumeUp(channel):
    # print("vol up")
    global currentVolume
    currentVolume = min(currentVolume + 10, 100)
    setVolume(currentVolume)

def volumeDown(channel):
    # print("vol down")
    global currentVolume
    currentVolume = max(0, currentVolume - 10)
    setVolume(currentVolume)

# TODO: set this by defined GOIO inputs (bananas)
def setPlayerMode(mode):
    global playerMode
    global soundPlayer
    playerMode = mode
    if playerMode == PlayerMode.MUSIC:
        soundPlayer.setList("./Sounds/Music/01/*.mp3")
    elif playerMode == PlayerMode.ANIMALS:
        soundPlayer = SamplePlayer(mpgPlayer, "./Sounds/Animals")
        soundPlayer.setList("./Sounds/Animals/*.mp3")
    elif playerMode == PlayerMode.INSTRUMENT:
        print("PlayerMode.INSTRUMENT active!")
        soundPlayer = SamplePlayer(mpgPlayer, "./Sounds/Instruments")
        soundPlayer.setList("./Sounds/Instruments/01/*.mp3")
    elif playerMode == PlayerMode.ONLINE:
        print("PlayerMode.ONLINE active")
        soundPlayer = OnlinePlayer(mpgPlayer, "")

    else:
        soundPlayer.setList("./Sounds/Music/01*.mp3")

def nextPlayerMode():
    global playerMode
    playerMode = (playerMode + 1) % len(PlayerMode)
    print("mode: " + str(playerMode))
    setPlayerMode(playerMode)

GPIO.setup(Input.INPUT_FWD, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_PRV, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_PLAY_PAUSE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_MUSIC_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_ANIMAL_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_INSTRUMENT_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_ONLINE_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# -------- GPIO input functions --------
def inputForward(channel):
    # nextSong()
    # GPIO.output(LED_FWD, 1)
    print("INPUT inputForward")
    soundPlayer.playNext()

def inputPrevious(channel):
    # GPIO.output(LED_FWD, 0)
    # previousSong()
    print("INPUT inputPrevious")
    soundPlayer.playPrevious()

def playPausePlayer(self):
    soundPlayer.playPausePlayer()

def inputModeChange(channel):
    print("INPUT mode change")
    soundPlayer.pausePlayer()
    nextPlayerMode()

# -------- program start --------
# default volume on startup
setVolume(currentVolume)

# sound played on startup
startupSound = "./Sounds/System/TurnOn.mp3"

# play startup sound
soundPlayer.playSong(startupSound)
# sleep(2)
# soundPlayer.playSong("http://live-radio02.mediahubaustralia.com/2FMW/mp3")

GPIO.add_event_detect(Input.INPUT_FWD, GPIO.RISING, callback=inputForward, bouncetime=300)
GPIO.add_event_detect(Input.INPUT_PRV, GPIO.RISING, callback=inputPrevious, bouncetime=300)
GPIO.add_event_detect(Input.INPUT_PLAY_PAUSE, GPIO.RISING, callback=playPausePlayer, bouncetime=300)
# GPIO.add_event_detect(Input.INPUT_MODE_CHG, GPIO.RISING, callback=inputModeChange, bouncetime=300)
# GPIO.add_event_detect(Input.INPUT_VOL_UP, GPIO.RISING, callback=volumeUp, bouncetime=300)
# GPIO.add_event_detect(Input.INPUT_VOL_DOWN, GPIO.RISING, callback=volumeDown, bouncetime=300)

# loop until termination
while True:
    sleep(1)