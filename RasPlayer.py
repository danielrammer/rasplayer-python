#!/usr/bin/python
from math import fabs
import glob
import subprocess
import RPi.GPIO as GPIO
from time import sleep
from enum import IntEnum
from mpyg321.MPyg123Player import MPyg123Player # or MPyg321Player if you installed mpg321

## -------- HOW TO RUN THAT STUFF --------
# RUN: xvfb-run python RasPlayer.py
# set volume
# amixer sset 'Master' 50%
# ----------------------------------------

GPIO.setmode(GPIO.BCM)      # Set's GPIO pins to BCM (logic) GPIO numbering

# -------- types --------
class PlayerMode(IntEnum):
    MUSIC = 0
    ANIMALS = 1

class Input(IntEnum):
    INPUT_FWD = 17
    # LED_FWD = 23
    # INPUT_PRV = 27
    # INPUT_MODE_CHG = 27
    INPUT_VOL_UP = 27
    INPUT_VOL_DOWN = 22
    NONE = 1337
player = MPyg123Player()
filelist = ""
currentSong = 0
currentVolume = 60
playerMode = PlayerMode.MUSIC

GPIO.setup(Input.INPUT_FWD, GPIO.IN)
# GPIO.setup(LED_FWD, GPIO.OUT)
# GPIO.setup(INPUT_PRV, GPIO.IN)
# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN)
GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN)
GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN)

# -------- function definitions --------
def nextSong():
    global filelist
    global currentSong
    currentSong = (currentSong + 1) % numberOfSongs
    print("play: " + filelist[currentSong])
    player.stop() # TODO: check if necessary
    player.play_song(filelist[currentSong])

def previousSong():
    global filelist
    global currentSong
    currentSong = max((currentSong - 1), 0)
    print("play: " + filelist[currentSong])
    player.stop() # TODO: check if necessary
    player.play_song(filelist[currentSong])

# other control functions
def pausePlayer():
    print("pause")
    player.pause()

def setVolume(vol):
    print("set volume to " + str(vol))
    subprocess.call(["amixer", "-D", "default", "sset", "Master", str(vol)+"%"], stdout=subprocess.DEVNULL)

def selectList(path):
    global filelist
    global numberOfSongs
    global currentSong
    currentSong = -1
    filelist = glob.glob(path)
    filelist.sort()
    numberOfSongs = len(filelist)
    print("selected list: " + str(filelist))

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

def setPlayerMode(mode):
    global playerMode
    playerMode = mode
    if playerMode == PlayerMode.MUSIC:
        selectList("./Sounds/Music/*.mp3")
    elif playerMode == PlayerMode.ANIMALS:
        selectList("./Sounds/Animals/*.mp3")
    else:
        selectList("./Sounds/Music/*.mp3")

def nextPlayerMode():
    global playerMode
    playerMode = (playerMode + 1) % len(PlayerMode)
    print("mode: " + str(playerMode))
    setPlayerMode(playerMode)

GPIO.setup(Input.INPUT_FWD, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_PRV, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# -------- GPIO input functions --------
def inputNxtSong(channel):
    nextSong()
    # GPIO.output(LED_FWD, 1)
    print("INPUT next")
def inputPrvSong(channel):
    # GPIO.output(LED_FWD, 0)
    previousSong()
    print("INPUT prev")
def inputModeChange(channel):
    print("INPUT mode change")
    pausePlayer()
    nextPlayerMode()

# -------- program start --------
# sound played on startup
startupSound = "./Sounds/System/TurnOn.mp3"
# set initial file list - probably music list
setPlayerMode(PlayerMode.MUSIC)
setVolume(currentVolume)

# play startup sound
player.play_song(startupSound)

GPIO.add_event_detect(Input.INPUT_FWD, GPIO.RISING, callback=inputNxtSong, bouncetime=300)
# GPIO.add_event_detect(INPUT_PRV, GPIO.RISING, callback=inputPrvSong, bouncetime=300)
# GPIO.add_event_detect(Input.INPUT_MODE_CHG, GPIO.RISING, callback=inputModeChange, bouncetime=300)
GPIO.add_event_detect(Input.INPUT_VOL_UP, GPIO.RISING, callback=volumeUp, bouncetime=300)
GPIO.add_event_detect(Input.INPUT_VOL_DOWN, GPIO.RISING, callback=volumeDown, bouncetime=300)

# loop until termination
while True:
    sleep(1)