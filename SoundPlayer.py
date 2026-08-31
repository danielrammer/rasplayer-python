#!/usr/bin/python
import glob
from collections import deque
import subprocess
import threading
import time
from enum import IntEnum


def make_generic_input_event(channel, inputs, level_reader, observed_at=None):
    """Capture the GPIO level so press/release semantics survive queueing."""
    try:
        button = inputs.index(channel)
    except ValueError:
        return None
    level = 1 if level_reader(channel) else 0
    return {
        "button": button,
        "channel": int(channel),
        "level": level,
        "pressed": level == 1,
        "edge": "press" if level else "release",
        "input_at": time.monotonic() if observed_at is None else observed_at,
    }


def route_generic_input(event, mode_name, active, generation):
    """Route press-only selectors separately from stateful generic buttons."""
    if active and mode_name in ("MUSIC", "ONLINE"):
        if not event["pressed"]:
            return None
        selection = dict(event)
        selection["mode"] = mode_name
        selection["generation"] = generation
        return "selection", selection
    return "generic", event


def apply_generic_input(player, mode_name, event):
    """Apply one explicit edge according to the active mode's semantics."""
    if event["pressed"]:
        return "press", player.buttonDown(event["button"])
    if mode_name == "SYNTH" and hasattr(player, "buttonUp"):
        return "release", player.buttonUp(event["button"])
    return "release_ignored", False


class FeedbackPlayer:
    """Serialize short mpg123 UI sounds without occupying the owner thread."""

    SOUNDS = {
        "generic": "./Sounds/System/0/generic.mp3",
        "mode_switch": "./Sounds/System/0/mode-switch.mp3",
        "volume_down": "./Sounds/System/0/vol-down.mp3",
        "volume_max": "./Sounds/System/0/vol-max.mp3",
        "volume_up": "./Sounds/System/0/vol-up.mp3",
    }

    def __init__(self, process_factory=None):
        self._requests = deque()
        self._request_condition = threading.Condition()
        self._max_requests = 16
        self._superseded = 0
        self._stop = threading.Event()
        self._process_lock = threading.Lock()
        self._process = None
        self._process_factory = process_factory or subprocess.Popen
        self._thread = threading.Thread(
            target=self._run, name="rasplayer-feedback", daemon=True)
        self._thread.start()

    def play(self, name, count=1, interval=0.0, source="action",
             category=None):
        path = self.SOUNDS.get(name)
        if path is None:
            print("FEEDBACK rejected name=%s reason=unknown" % name, flush=True)
            return False
        enqueued_at = time.monotonic()
        request = (name, path, count, interval, enqueued_at, source, category)
        with self._request_condition:
            if category is not None:
                for index, pending in enumerate(self._requests):
                    if pending[6] == category:
                        self._requests[index] = request
                        self._superseded += 1
                        print("FEEDBACK supersede category=%s name=%s "
                              "source=%s depth=%d superseded=%d" %
                              (category, name, source, len(self._requests),
                               self._superseded), flush=True)
                        self._request_condition.notify()
                        return True
            if len(self._requests) >= self._max_requests:
                print("FEEDBACK drop name=%s reason=queue_full" % name,
                      flush=True)
                return False
            self._requests.append(request)
            print("FEEDBACK enqueue name=%s source=%s uptime=%.6f count=%d "
                  "depth=%d category=%s" %
                  (name, source, enqueued_at, count,
                   len(self._requests), category), flush=True)
            self._request_condition.notify()
            return True

    def _run(self):
        while not self._stop.is_set():
            with self._request_condition:
                if not self._requests and not self._stop.is_set():
                    self._request_condition.wait(0.1)
                if self._stop.is_set():
                    break
                if not self._requests:
                    continue
                request = self._requests.popleft()
            name, path, count, interval, enqueued_at, source, category = request
            try:
                for index in range(count):
                    if self._stop.is_set():
                        break
                    started = time.monotonic()
                    print("FEEDBACK play_begin name=%s source=%s uptime=%.6f "
                          "item=%d queue_wait_ms=%.3f" %
                          (name, source, started, index + 1,
                           (started - enqueued_at) * 1000.0), flush=True)
                    process = self._process_factory(
                        ["mpg123", "-q", "-o", "alsa", path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    with self._process_lock:
                        self._process = process
                    try:
                        _, error = process.communicate(timeout=3.0)
                        error = error.decode(errors="replace").strip()
                    except subprocess.TimeoutExpired:
                        process.kill()
                        _, error = process.communicate()
                        error = "timeout: " + error.decode(
                            errors="replace").strip()
                    finally:
                        with self._process_lock:
                            self._process = None
                    print("FEEDBACK play_complete name=%s source=%s item=%d "
                          "duration_ms=%.3f returncode=%s stderr=%r" %
                          (name, source, index + 1,
                           (time.monotonic() - started) * 1000.0,
                           process.returncode, error), flush=True)
                    if index + 1 < count and self._stop.wait(interval):
                        break
            except Exception as exc:
                print("FEEDBACK exception name=%s error=%r" % (name, exc),
                      flush=True)

    def close(self):
        self._stop.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        with self._request_condition:
            self._request_condition.notify_all()
        self._thread.join(timeout=0.5)

class SoundPlayerBase:
    # GPIO callbacks must remain tiny.  RasPlayer installs this dispatcher so
    # callbacks only enqueue commands for its single state-owner thread.
    input_dispatcher = None
    player = None
    is_playing = False
    filelist = ""
    numberOfItemsInList = 0
    currentFileNum = -1 # TODO: this is the type (e.g. pig sound)
    # currentFile = 0     # TODO: this is the actual sound file (e.g. pig sound #2)

    # input mapping to GPIO BCM
    class GenericInput(IntEnum):
        IN_1 = 11
        IN_2 = 5
        IN_3 = 6
        IN_4 = 19
        IN_5 = 16

    inputs = [GenericInput.IN_1, 
              GenericInput.IN_2,
              GenericInput.IN_3,
              GenericInput.IN_4,
              GenericInput.IN_5]

    def __init__(self, vlcInstance, player, path):
        # print("SoundPlayerBase Instantiated ModeHandler")
        print("SoundPlayerBase initialized with path: " + path)
        self.vlcInstance = vlcInstance
        self.player = player
        self.is_playing = False
        # self.setList(path)
        # self.pausePlayer()

    # def stopPlayer(self):
    #     print("SoundPlayer: stopping player")
    #     state = self.player.get_state()
    #     if state in (vlc.State.Playing, vlc.State.Paused):
    #         self.player.stop()
    #         print("SoundPlayer: player stopped")
    #     self.is_playing = False

    @classmethod
    def _generic_callback(cls, channel):
        # Capture the physical level in the callback. The owner decides
        # whether this edge is a one-shot press or Synth state transition.
        import RPi.GPIO as GPIO
        event = make_generic_input_event(channel, cls.inputs, GPIO.input)
        if event is not None and cls.input_dispatcher is not None:
            cls.input_dispatcher("generic", event)

    # TODO: make 2D array to allow more sounds per type
    def setList(self, path):
        self.currentFileNum = 0
        self.filelist = glob.glob(path)
        self.filelist.sort()
        self.numberOfItemsInList = len(self.filelist)
        print("selected list in mgr: " + str(self.filelist))


    def playSong(self, path):
        print("play song: " + str(path))

        media = self.vlcInstance.media_new(path)
        self.player.set_media(media)
        self.player.play()
        self.is_playing = True

    def playNext(self):
        print("SoundPlayer playNext")
        # play first if list was newly selected
        # TODO: distinguish between currentFileType and currentFile in the future
        if self.currentFileNum < 0:
            self.currentFileNum = 0
        else:
            self.currentFileNum = (self.currentFileNum + 1) % self.numberOfItemsInList

        self.currentSong = self.filelist[self.currentFileNum]
        print("play next: " + self.currentSong)

        media = self.vlcInstance.media_new(self.currentSong)
        self.player.set_media(media)
        self.player.play()
        self.is_playing = True

    def playPrevious(self):
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
        """Apply a coalesced list offset with one media open."""
        if not self.filelist:
            return False
        start = self.currentFileNum if self.currentFileNum >= 0 else 0
        self.currentFileNum = (start + offset) % self.numberOfItemsInList
        self.currentSong = self.filelist[self.currentFileNum]
        print("PLAYER navigate offset=%d from=%d to=%d" %
              (offset, start, self.currentFileNum), flush=True)
        media = self.vlcInstance.media_new(self.currentSong)
        self.player.set_media(media)
        self.player.play()
        self.is_playing = True
        return True

    def playPausePlayer(self): 
        import vlc
        state = self.player.get_state()
        if state == vlc.State.Playing:
            self.player.pause()
            return True
        elif state == vlc.State.Paused:
            self.player.play()
            return True
        return False
        
        
        # if self.is_playing:
        #     self.player.pause()
        #     self.is_playing = False

        #     print("SoundPlayer: pausing player at currentNum " + str(self.currentFileNum))
        # else:
        #     print("SoundPlayer: resuming currentNum " + str(self.currentFileNum))
        #     if (self.currentFileNum < 0):
        #         self.currentFileNum = 0
         
        #         self.currentSong = self.filelist[self.currentFileNum]

        #         print("play first song: " + self.currentSong)

        #         media = self.vlcInstance.media_new(self.currentSong)
        #         self.player.set_media(media)
        #         self.player.play()
        #     else:
        #         self.player.play()
        
        #     self.is_playing = True
        #     print("SoundPlayer: resuming player")

    def pausePlayer(self):
        self.is_playing = False
        self.player.pause()

    def buttonDown(self, buttonNumber):
        print("pressed generic button " + str(buttonNumber))
        self.currentFileNum = 0
        print("play: " + self.filelist[buttonNumber])

        media = self.vlcInstance.media_new(self.filelist[buttonNumber])
        self.player.set_media(media)
        self.player.play()
        self.is_playing = True

    def is_playing_now(self):
        return self.is_playing
    
    def update(self):
        pass
