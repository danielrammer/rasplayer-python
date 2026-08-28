
import time
import signal
import sys
from command_path import SerializedCommandPath
from systemd_notify import WatchdogNotifier

startup_t0 = time.monotonic()
shutting_down = False

def startup_mark(label):
    print("STARTUP %s elapsed=%.3f" % (label, time.monotonic() - startup_t0), flush=True)

startup_mark("python_entry")
watchdog = WatchdogNotifier()

from SoundPlayer import SoundPlayerBase
import glob
import subprocess
import RPi.GPIO as GPIO
from enum import IntEnum
from time import sleep
startup_mark("minimum_imports_complete")

## -------- HOW TO RUN THAT STUFF --------
# RUN: xvfb-run python RasPlayer.py
# set volume
# amixer sset 'Master' 50%
# ----------------------------------------

# System Sounds:
# 0 - TurnOn.mp3, 1 - vol-up.mp3, 2 - vol-down.mp3

def cleanup_and_exit(signum, frame):
    global shutting_down
    shutting_down = True
    print("Cleaning up GPIO and exiting.")
    if soundPlayer is not None and hasattr(soundPlayer, "stop"):
        try:
            soundPlayer.stop()
        except Exception as exc:
            print("Cleanup player failed: %s" % exc, flush=True)
    if vlcPlayer is not None:
        try:
            vlcPlayer.release()
        except Exception:
            pass
    if vlcInstance is not None:
        try:
            vlcInstance.release()
        except Exception:
            pass
    stop_startup_process()
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
    SYNTH = 4
    NONE = 5

# these inputs are global - work for all modes
# maybe fwd and prv are not available for all
class Input(IntEnum):
    INPUT_PLAY_PAUSE = 4
    INPUT_SONIC_TRIGGER = 14
    INPUT_SONIC_ECHO = 15
    INPUT_FWD = 17
    INPUT_PRV = 27
    # INPUT_MODE_CHG = 27 # will be wire (banana)
    INPUT_VOL_UP = 22
    INPUT_VOL_DOWN = 23
    INPUT_MUSIC_MODE = 24
    INPUT_ONLINE_MODE = 10
    # INPUT_ANIMAL_MODE = 9
    INPUT_INSTRUMENT_MODE = 25
    OUTPUT_STATUS_LED = 26
    INPUT_SYNTH_MODE = 9

    NONE = 1337

vlcInstance = None
vlcPlayer = None
samplePlayer = None
startup_process = None

def play_startup_sound():
    """Start and validate the required startup MP3 without importing pygame."""
    global startup_process
    try:
        startup_process = subprocess.Popen(
            ["mpg123", "-q", "-o", "alsa", "./Sounds/System/0/TurnOn.mp3"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        sleep(0.10)
        result = startup_process.poll()
        if result is not None and result != 0:
            error = startup_process.stderr.read().decode(errors="replace").strip()
            raise RuntimeError("mpg123 exited %s: %s" % (result, error))
        print("startup sound triggered via mpg123", flush=True)
        return True
    except Exception as exc:
        print("Startup sound failed: %s" % exc, flush=True)
        return False

def ensure_sample_player():
    """Load pygame/system samples only when a later control needs them."""
    global samplePlayer, startup_process
    if samplePlayer is not None:
        return samplePlayer
    stop_startup_process()
    from SamplePlayer import SamplePlayer
    samplePlayer = SamplePlayer(vlcInstance, vlcPlayer, "./Sounds/System", 1, True)
    return samplePlayer

def stop_startup_process():
    global startup_process
    if startup_process is not None and startup_process.poll() is None:
        startup_process.terminate()
        try:
            startup_process.wait(timeout=1)
        except Exception:
            startup_process.kill()

def ensure_vlc():
    global vlcInstance, vlcPlayer
    if vlcInstance is None:
        startup_mark("vlc_init_begin")
        import vlc
        vlcInstance = vlc.Instance("--aout=alsa")
        vlcPlayer = vlcInstance.media_player_new()
        startup_mark("vlc_init_complete")
    return vlcInstance, vlcPlayer

filelist = ""
currentSong = 0
currentVolume = 80
soundPlayer = None
playerMode = PlayerMode.NONE
distance_counter = 0
mode_state = "NONE"
command_path = None

def enqueue_command(command, value=None):
    """Fast GPIO/VLC producer path; all state mutation happens in worker."""
    if command_path is not None and command_path.submit(command, value):
        return
    if command_path is not None:
        print("INPUT command queue full; dropping %s" % command, flush=True)

def _stop_player(player):
    if player is None:
        return
    try:
        player.stop()
    except Exception as exc:
        print("Player stop failed: %s" % exc, flush=True)

def _process_command(command, value):
    global mode_state
    if shutting_down:
        return
    if command == "mode":
        setPlayerMode(value)
    elif command == "next" and soundPlayer is not None:
        soundPlayer.playNext()
    elif command == "previous" and soundPlayer is not None:
        soundPlayer.playPrevious()
    elif command == "play_pause" and soundPlayer is not None:
        soundPlayer.playPausePlayer()
    elif command == "volume_up":
        volumeUp(None)
    elif command == "volume_down":
        volumeDown(None)
    elif command == "generic" and soundPlayer is not None:
        soundPlayer.buttonDown(value)

def _command_tick():
    if shutting_down:
        return
    watchdog.heartbeat()
    if soundPlayer is not None and hasattr(soundPlayer, "update"):
        soundPlayer.update()

# -------- GPIO setup --------
GPIO.setup(Input.INPUT_PLAY_PAUSE, GPIO.IN)

GPIO.setup(Input.INPUT_FWD, GPIO.IN)
GPIO.setup(Input.INPUT_PRV, GPIO.IN)

GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN)
GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN)

GPIO.setup(Input.INPUT_MUSIC_MODE, GPIO.IN)
GPIO.setup(Input.INPUT_ONLINE_MODE, GPIO.IN)
# GPIO.setup(Input.INPUT_ANIMAL_MODE, GPIO.IN)
GPIO.setup(Input.INPUT_INSTRUMENT_MODE, GPIO.IN)

GPIO.setup(Input.OUTPUT_STATUS_LED, GPIO.OUT)

GPIO.setup(Input.INPUT_SONIC_TRIGGER, GPIO.OUT)
GPIO.setup(Input.INPUT_SONIC_ECHO, GPIO.IN)
startup_mark("gpio_ready")

# -------- function definitions --------
# other control functions
def setVolume(vol):
    global samplePlayer
    print("set volume to " + str(vol))
    # subprocess.call(["amixer", "-D", "default", "sset", "Master", str(vol)+"%"], stdout=subprocess.DEVNULL)
    command  = ['amixer', '-c', '0', 'sset', 'PCM',  str(vol)+'%']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def volumeUp(channel):
    # print("vol up")
    global currentVolume
    samples = ensure_sample_player().samples
    maxVolumeReached = currentVolume >= 100

    if maxVolumeReached:
        print("VOL MAX: " + str(samples[0]))
        samples[1].play()
        sleep(0.1)
        samples[1].play()
    else:
        currentVolume = min(currentVolume + 10, 100)
        setVolume(currentVolume)
        sleep(0.05)
        samplePlayer.samples[1].play()


def volumeDown(channel):
    # print("vol down")
    global currentVolume
    samples = ensure_sample_player().samples
    currentVolume = max(50, currentVolume - 10)
    samples[2].play()
    setVolume(currentVolume)

def get_distance():
    # Ensure trigger is low
    GPIO.output(Input.INPUT_SONIC_TRIGGER, False)
    time.sleep(0.002)

    # Send 10µs trigger pulse
    GPIO.output(Input.INPUT_SONIC_TRIGGER, True)
    time.sleep(0.00001)
    GPIO.output(Input.INPUT_SONIC_TRIGGER, False)

    timeout = time.time() + 0.05  # 20 ms max wait
    # Wait for echo start
    start_time = time.time()
    while GPIO.input(Input.INPUT_SONIC_ECHO) == 0:  
        start_time = time.time()
        if time.time() > timeout:
            # print("Echo start timeout")
            break  # Timeout

    timeout = time.time() + 0.02  # 20 ms max wait
    # Wait for echo end
    end_time = time.time()
    while GPIO.input(Input.INPUT_SONIC_ECHO) == 1:
        end_time = time.time()
        if time.time() > timeout:
            # print("Echo end timeout")
            break  # Timeout

    # Calculate distance
    elapsed = end_time - start_time
    distance = (elapsed * 34300) / 2  # cm

    # print(f"D: {distance:.2f} cm")
    return distance

# TODO: set this by defined GOIO inputs (bananas)
def setPlayerMode(mode):
    global playerMode
    global soundPlayer
    global mode_state

    mode = PlayerMode(mode)

    if (playerMode == mode and mode_state == "ACTIVE"):
        print("setPlayerMode: already in mode " + str(mode))
        return
    

    mode_state = "STOPPING"
    old_player = soundPlayer
    soundPlayer = None
    if old_player is not None:
        print("SoundPlayer: stopping player")
        _stop_player(getattr(old_player, "player", None))
        if hasattr(old_player, "stop"):
            try:
                old_player.stop()
            except Exception as exc:
                print("Mode cleanup failed: %s" % exc, flush=True)
        print("SoundPlayer: player stopped")
        sleep(0.2)

    startup_mark("mode_%s_init_begin" % mode.name)
    playerMode = mode
    mode_state = "INITIALIZING"
    try:
        # Every non-system mode uses the shared VLC player, including sample
        # modes (their generic-button handler stops it before pygame playback).
        vlc_instance, vlc_player = ensure_vlc()
        if playerMode == PlayerMode.MUSIC:
            from MusicPlayer import MusicPlayer
            soundPlayer = MusicPlayer(vlc_instance, vlc_player, "./Sounds/Music/02")
        elif playerMode == PlayerMode.ANIMALS:
            stop_startup_process()
            from SamplePlayer import SamplePlayer
            soundPlayer = SamplePlayer(vlc_instance, vlc_player, "./Sounds/Animals", 3)
        elif playerMode == PlayerMode.INSTRUMENT:
            print("PlayerMode.INSTRUMENT active!")
            stop_startup_process()
            from SamplePlayer import SamplePlayer
            soundPlayer = SamplePlayer(vlc_instance, vlc_player, "./Sounds/Instruments", 5)
        elif playerMode == PlayerMode.ONLINE:
            print("PlayerMode.ONLINE active")
            from OnlinePlayer import OnlinePlayer
            soundPlayer = OnlinePlayer(vlc_instance, vlc_player, "")
        elif playerMode == PlayerMode.SYNTH:
            print("PlayerMode.SYNTH active")
            from SynthPlayer import SynthPlayer
            soundPlayer = SynthPlayer(vlc_instance, vlc_player, "", get_distance)
        elif playerMode == PlayerMode.NONE:
            soundPlayer = None
        else:
            soundPlayer = None
        startup_mark("mode_%s_init_complete" % mode.name)
        mode_state = "ACTIVE"
    except Exception as exc:
        # A failed optional mode must not take down the local control loop.
        print("Mode %s initialization failed: %s" % (mode.name, exc), flush=True)
        playerMode = PlayerMode.NONE
        soundPlayer = None
        mode_state = "FAILED"
        startup_mark("mode_%s_init_failed" % mode.name)

def nextPlayerMode():
    global playerMode
    playerMode = (playerMode + 1) % len(PlayerMode)
    print("mode: " + str(playerMode))
    setPlayerMode(playerMode)

GPIO.setup(Input.INPUT_PLAY_PAUSE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.setup(Input.INPUT_FWD, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_PRV, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.setup(Input.INPUT_VOL_UP, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_VOL_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.setup(Input.INPUT_MUSIC_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
# GPIO.setup(Input.INPUT_ANIMAL_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_INSTRUMENT_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(Input.INPUT_ONLINE_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.setup(Input.INPUT_SYNTH_MODE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# -------- GPIO input functions --------
def inputForward(channel):
    # nextSong()
    # GPIO.output(LED_FWD, 1)
    print("INPUT inputForward")
    enqueue_command("next")

def inputPrevious(channel):
    # GPIO.output(LED_FWD, 0)
    # previousSong()
    print("INPUT inputPrevious")
    enqueue_command("previous")

def playPausePlayer(self):
    print("INPUT pause/play")
    enqueue_command("play_pause")

def inputModeChange(channel):
    print("INPUT mode change")
    enqueue_command("mode", (playerMode + 1) % len(PlayerMode))

# -------- program start --------
# default volume on startup
setVolume(currentVolume)

# sound played on startup
# startupSound = "./Sounds/System/0/TurnOn.mp3"

GPIO.output(Input.OUTPUT_STATUS_LED, 1)  # turn on status LED

# play startup sound through the lightweight decoder; pygame is deferred.
if not play_startup_sound():
    print("Startup sound backend unavailable; continuing with local controls", flush=True)
startup_mark("audio_ready")
startup_mark("system_sounds_ready")
# soundPlayer.playSong("http://live-radio02.mediahubaustralia.com/2FMW/mp3")


GPIO.add_event_detect(Input.INPUT_PLAY_PAUSE, GPIO.RISING, callback=playPausePlayer, bouncetime=500)

GPIO.add_event_detect(Input.INPUT_FWD, GPIO.RISING, callback=inputForward, bouncetime=500)
GPIO.add_event_detect(Input.INPUT_PRV, GPIO.RISING, callback=inputPrevious, bouncetime=500)

# GPIO.add_event_detect(Input.INPUT_MODE_CHG, GPIO.RISING, callback=inputModeChange, bouncetime=300)
GPIO.add_event_detect(Input.INPUT_VOL_UP, GPIO.RISING, callback=lambda x: enqueue_command("volume_up"), bouncetime=500)
GPIO.add_event_detect(Input.INPUT_VOL_DOWN, GPIO.RISING, callback=lambda x: enqueue_command("volume_down"), bouncetime=500)

GPIO.add_event_detect(Input.INPUT_MUSIC_MODE, GPIO.RISING, callback=lambda x : enqueue_command("mode", PlayerMode.MUSIC), bouncetime=1000)
GPIO.add_event_detect(Input.INPUT_ONLINE_MODE, GPIO.RISING, callback=lambda x : enqueue_command("mode", PlayerMode.ONLINE), bouncetime=1000)
# GPIO.add_event_detect(Input.INPUT_ANIMAL_MODE, GPIO.RISING, callback=lambda x :setPlayerMode(PlayerMode.ANIMALS), bouncetime=1000)
GPIO.add_event_detect(Input.INPUT_INSTRUMENT_MODE, GPIO.RISING, callback=lambda x :enqueue_command("mode", PlayerMode.INSTRUMENT), bouncetime=1000)

GPIO.add_event_detect(Input.INPUT_SYNTH_MODE, GPIO.RISING, callback=lambda x : enqueue_command("mode", PlayerMode.SYNTH), bouncetime=1000)
SoundPlayerBase.input_dispatcher = enqueue_command
command_path = SerializedCommandPath(_process_command, _command_tick)
command_path.start()
startup_mark("callbacks_registered")
startup_mark("LOCAL_READY")
watchdog.ready()

# loop until termination
while True:
    # distance_counter += 1
    # if distance_counter % 10 == 0:
    #     distance = get_distance()
        # print(f"Distance: {distance:.2f} cm")

    # if soundPlayer is not None:
    #     soundPlayer.update()
    # Player state is owned by _command_worker; this loop only keeps the
    # process alive and lets signal handlers run.
    # print("main loop: playerMode " + str(playerMode))
    sleep(0.05)
