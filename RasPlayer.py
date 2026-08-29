
import time
import signal
import sys
import threading
import traceback
from command_path import SerializedCommandPath
from systemd_notify import WatchdogNotifier

startup_t0 = time.monotonic()
shutting_down = False

def startup_mark(label):
    now = time.monotonic()
    elapsed = now - startup_t0
    print("STARTUP %s elapsed=%.3f uptime=%.3f" % (label, elapsed, now), flush=True)
    try:
        with open("/run/boottrace/events.log", "a") as stream:
            stream.write(
                "BOOTTRACE uptime=%.3f event=rasplayer_%s detail=elapsed=%.3f\n"
                % (now, label, elapsed))
    except OSError:
        pass

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
samplePlayer = None
startup_process = None
vlc_init_lock = threading.Lock()

def play_startup_sound():
    """Start and validate the required startup MP3 without importing pygame."""
    global startup_process
    try:
        startup_mark("mpg123_launch_begin")
        startup_process = subprocess.Popen(
            ["mpg123", "-q", "-o", "alsa", "./Sounds/System/0/TurnOn.mp3"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        startup_mark("mpg123_process_started")
        sleep(0.10)
        result = startup_process.poll()
        if result is not None and result != 0:
            error = startup_process.stderr.read().decode(errors="replace").strip()
            raise RuntimeError("mpg123 exited %s: %s" % (result, error))
        startup_mark("mpg123_launch_validated")
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
    samplePlayer = SamplePlayer(vlcInstance, None, "./Sounds/System", 1, True)
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
    global vlcInstance
    with vlc_init_lock:
        if vlcInstance is None:
            startup_mark("vlc_init_begin")
            import vlc
            vlcInstance = vlc.Instance(
                "--aout=alsa", "--network-caching=1000", "--http-reconnect")
            startup_mark("vlc_init_complete")
        # Do not reuse the player that may still be closing a network stream.
        return vlcInstance, vlcInstance.media_player_new()

filelist = ""
currentSong = 0
currentVolume = 80
soundPlayer = None
playerMode = PlayerMode.NONE
distance_counter = 0
mode_state = "NONE"
command_path = None
mode_generation = 0
ultrasonic_timeout_count = 0
ultrasonic_last_timeout_log = 0.0

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

def _cleanup_mode_backend(player, mode, reason, done=None):
    """Run potentially blocking backend teardown away from the owner thread."""
    started = time.monotonic()
    print("MODE stop_begin mode=%s reason=%s uptime=%.6f" %
          (mode.name, reason, started), flush=True)
    try:
        used_mode_stop = False
        if player is not None and hasattr(player, "stop"):
            used_mode_stop = True
            player.stop()
        backend_player = getattr(player, "player", None)
        if backend_player is not None:
            if not used_mode_stop:
                backend_player.stop()
            try:
                backend_player.release()
            except Exception:
                pass
        print("MODE stop_complete mode=%s reason=%s uptime=%.6f duration_ms=%.3f" %
              (mode.name, reason, time.monotonic(),
               (time.monotonic() - started) * 1000.0), flush=True)
    except Exception as exc:
        print("MODE stop_exception mode=%s reason=%s uptime=%.6f "
              "duration_ms=%.3f error=%r\n%s" %
              (mode.name, reason, time.monotonic(),
               (time.monotonic() - started) * 1000.0, exc,
               traceback.format_exc()), flush=True)
    finally:
        if done is not None:
            done.set()

def _release_pygame_for_synth():
    started = time.monotonic()
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.stop()
            pygame.mixer.quit()
        print("SYNTH pygame_release_complete uptime=%.6f duration_ms=%.3f" %
              (time.monotonic(),
               (time.monotonic() - started) * 1000.0), flush=True)
    except Exception as exc:
        print("SYNTH pygame_release_exception error=%r" % (exc,), flush=True)

def _prepare_mode(mode, generation, requested_at, cleanup_done,
                  wait_for_cleanup):
    """Prepare a backend without blocking serialized input/state ownership."""
    started = time.monotonic()
    player = None
    vlc_player = None
    error = None
    print("MODE init_worker_begin mode=%s generation=%d uptime=%.6f" %
          (mode.name, generation, started), flush=True)
    try:
        if wait_for_cleanup and cleanup_done is not None:
            wait_started = time.monotonic()
            cleanup_done.wait(timeout=5.0)
            print("MODE cleanup_wait mode=%s generation=%d duration_ms=%.3f complete=%s" %
                  (mode.name, generation,
                   (time.monotonic() - wait_started) * 1000.0,
                   cleanup_done.is_set()), flush=True)
        if mode == PlayerMode.SYNTH:
            _release_pygame_for_synth()

        vlc_instance, vlc_player = ensure_vlc()
        if mode == PlayerMode.MUSIC:
            from MusicPlayer import MusicPlayer
            player = MusicPlayer(vlc_instance, vlc_player, "./Sounds/Music/02")
        elif mode == PlayerMode.ANIMALS:
            from SamplePlayer import SamplePlayer
            player = SamplePlayer(vlc_instance, vlc_player, "./Sounds/Animals", 3)
        elif mode == PlayerMode.INSTRUMENT:
            from SamplePlayer import SamplePlayer
            player = SamplePlayer(vlc_instance, vlc_player, "./Sounds/Instruments", 5)
        elif mode == PlayerMode.ONLINE:
            from OnlinePlayer import OnlinePlayer
            player = OnlinePlayer(vlc_instance, vlc_player, "")
        elif mode == PlayerMode.SYNTH:
            from SynthPlayer import SynthPlayer
            player = SynthPlayer(vlc_instance, vlc_player, "", get_distance)
    except Exception as exc:
        error = "%r\n%s" % (exc, traceback.format_exc())
        if player is None and vlc_player is not None:
            try:
                vlc_player.release()
            except Exception:
                pass
    completed = time.monotonic()
    print("MODE init_worker_complete mode=%s generation=%d uptime=%.6f "
          "duration_ms=%.3f result=%s" %
          (mode.name, generation, completed, (completed - started) * 1000.0,
           "error" if error else "ok"), flush=True)
    enqueue_command("_mode_ready", {
        "mode": mode, "generation": generation, "player": player,
        "error": error, "requested_at": requested_at,
        "worker_started": started, "worker_completed": completed,
    })

def _accept_mode_ready(result):
    global soundPlayer, playerMode, mode_state
    mode = result["mode"]
    generation = result["generation"]
    if generation != mode_generation or playerMode != mode:
        print("MODE stale_completion mode=%s generation=%d current_generation=%d" %
              (mode.name, generation, mode_generation), flush=True)
        if result["player"] is not None:
            threading.Thread(
                target=_cleanup_mode_backend,
                args=(result["player"], mode, "stale_completion"),
                name="rasplayer-stale-cleanup", daemon=True).start()
        return
    if result["error"] is not None:
        print("MODE init_failed mode=%s generation=%d total_ms=%.3f error=%s" %
              (mode.name, generation,
               (time.monotonic() - result["requested_at"]) * 1000.0,
               result["error"]), flush=True)
        playerMode = PlayerMode.NONE
        soundPlayer = None
        mode_state = "FAILED"
        startup_mark("mode_%s_init_failed" % mode.name)
        return
    soundPlayer = result["player"]
    mode_state = "ACTIVE"
    print("MODE active mode=%s generation=%d total_ms=%.3f" %
          (mode.name, generation,
           (time.monotonic() - result["requested_at"]) * 1000.0), flush=True)
    startup_mark("mode_%s_init_complete" % mode.name)

def _process_command(command, value):
    global mode_state
    if shutting_down:
        return
    if command == "_mode_ready":
        _accept_mode_ready(value)
    elif command == "mode":
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
    global startup_process
    if startup_process is not None and startup_process.poll() is not None:
        startup_process = None
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
print("SYNTH ultrasonic_gpio_ready trigger=%d echo=%d" %
      (Input.INPUT_SONIC_TRIGGER, Input.INPUT_SONIC_ECHO), flush=True)
startup_mark("gpio_ready")

# -------- function definitions --------
# other control functions
def setVolume(vol):
    global samplePlayer
    started = time.monotonic()
    print("VOLUME set_begin volume=%s uptime=%.6f" % (vol, started), flush=True)
    # subprocess.call(["amixer", "-D", "default", "sset", "Master", str(vol)+"%"], stdout=subprocess.DEVNULL)
    command  = ['amixer', '-c', '0', 'sset', 'PCM',  str(vol)+'%']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("VOLUME set_complete volume=%s uptime=%.6f duration_ms=%.3f returncode=%d stderr=%r" %
          (vol, time.monotonic(), (time.monotonic() - started) * 1000.0,
           result.returncode, result.stderr.strip()), flush=True)

def volumeUp(channel):
    # print("vol up")
    global currentVolume
    samples = (None if playerMode == PlayerMode.SYNTH or
               mode_state in ("STOPPING", "INITIALIZING")
               else ensure_sample_player().samples)
    maxVolumeReached = currentVolume >= 100

    if maxVolumeReached:
        if samples is not None:
            print("VOL MAX: " + str(samples[0]))
            samples[1].play()
            sleep(0.1)
            samples[1].play()
    else:
        currentVolume = min(currentVolume + 10, 100)
        setVolume(currentVolume)
        sleep(0.05)
        if samples is not None:
            samples[1].play()


def volumeDown(channel):
    # print("vol down")
    global currentVolume
    samples = (None if playerMode == PlayerMode.SYNTH or
               mode_state in ("STOPPING", "INITIALIZING")
               else ensure_sample_player().samples)
    currentVolume = max(50, currentVolume - 10)
    if samples is not None:
        samples[2].play()
    setVolume(currentVolume)

def get_distance():
    global ultrasonic_timeout_count, ultrasonic_last_timeout_log
    measurement_started = time.monotonic()
    # Ensure trigger is low
    GPIO.output(Input.INPUT_SONIC_TRIGGER, False)
    time.sleep(0.002)

    # Send 10µs trigger pulse
    GPIO.output(Input.INPUT_SONIC_TRIGGER, True)
    time.sleep(0.00001)
    GPIO.output(Input.INPUT_SONIC_TRIGGER, False)

    timeout = time.monotonic() + 0.05
    # Wait for echo start
    start_time = time.monotonic()
    while GPIO.input(Input.INPUT_SONIC_ECHO) == 0:  
        start_time = time.monotonic()
        if time.monotonic() > timeout:
            ultrasonic_timeout_count += 1
            now = time.monotonic()
            if now - ultrasonic_last_timeout_log >= 5.0:
                print("SYNTH ultrasonic_timeout phase=start count=%d duration_ms=%.3f" %
                      (ultrasonic_timeout_count,
                       (now - measurement_started) * 1000.0), flush=True)
                ultrasonic_last_timeout_log = now
            return -1.0

    timeout = time.monotonic() + 0.02
    # Wait for echo end
    end_time = time.monotonic()
    while GPIO.input(Input.INPUT_SONIC_ECHO) == 1:
        end_time = time.monotonic()
        if time.monotonic() > timeout:
            ultrasonic_timeout_count += 1
            now = time.monotonic()
            if now - ultrasonic_last_timeout_log >= 5.0:
                print("SYNTH ultrasonic_timeout phase=end count=%d duration_ms=%.3f" %
                      (ultrasonic_timeout_count,
                       (now - measurement_started) * 1000.0), flush=True)
                ultrasonic_last_timeout_log = now
            return -1.0

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
    global mode_generation
    global samplePlayer

    mode = PlayerMode(mode)

    if (playerMode == mode and mode_state == "ACTIVE"):
        print("setPlayerMode: already in mode " + str(mode))
        return
    

    requested_at = time.monotonic()
    old_mode = playerMode
    old_player = soundPlayer
    soundPlayer = None
    mode_generation += 1
    generation = mode_generation
    cleanup_done = None
    if old_player is not None:
        mode_state = "STOPPING"
        cleanup_done = threading.Event()
        threading.Thread(
            target=_cleanup_mode_backend,
            args=(old_player, old_mode, "mode_switch", cleanup_done),
            name="rasplayer-mode-cleanup-%d" % generation,
            daemon=True).start()

    startup_mark("mode_%s_init_begin" % mode.name)
    playerMode = mode
    if mode == PlayerMode.NONE:
        mode_state = "NONE"
        return
    mode_state = "INITIALIZING"
    stop_startup_process()
    if mode == PlayerMode.SYNTH:
        # pygame keeps ALSA open after Sampler/system sounds. Invalidate the
        # cached sounds before the preparation worker closes that mixer.
        samplePlayer = None
    wait_for_cleanup = old_mode == PlayerMode.SYNTH or mode == PlayerMode.SYNTH
    threading.Thread(
        target=_prepare_mode,
        args=(mode, generation, requested_at, cleanup_done, wait_for_cleanup),
        name="rasplayer-mode-init-%d" % generation,
        daemon=True).start()

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

# Generic GPIO callbacks are process-owned and registered once. Mode
# constructors can therefore prepare on background threads without changing
# GPIO registrations or touching active application state.
for generic_input in SoundPlayerBase.inputs:
    GPIO.setup(generic_input, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# GPIO.setup(Input.INPUT_MODE_CHG, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# -------- GPIO input functions --------
def inputForward(channel):
    enqueue_command("next")

def inputPrevious(channel):
    enqueue_command("previous")

def playPausePlayer(self):
    enqueue_command("play_pause")

def inputModeChange(channel):
    enqueue_command("mode", (playerMode + 1) % len(PlayerMode))

# -------- program start --------
# default volume on startup
setVolume(currentVolume)

# sound played on startup
# startupSound = "./Sounds/System/0/TurnOn.mp3"

GPIO.output(Input.OUTPUT_STATUS_LED, 1)  # turn on status LED

# play startup sound through the lightweight decoder; pygame is deferred.
if not play_startup_sound():
    print("Startup mpg123 failed; using pygame fallback", flush=True)
    ensure_sample_player().samples[0].play()
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
for generic_input in SoundPlayerBase.inputs:
    GPIO.add_event_detect(
        generic_input, GPIO.RISING,
        callback=SoundPlayerBase._generic_callback, bouncetime=190)
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
