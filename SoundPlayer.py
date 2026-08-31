#!/usr/bin/python
import glob
import queue
import subprocess
import threading
import time
from enum import IntEnum


class FeedbackPlayer:
    """Serialize short mpg123 UI sounds without occupying the owner thread."""

    def __init__(self, process_factory=None):
        self._requests = queue.Queue(maxsize=16)
        self._stop = threading.Event()
        self._process_lock = threading.Lock()
        self._process = None
        self._process_factory = process_factory or subprocess.Popen
        self._thread = threading.Thread(
            target=self._run, name="rasplayer-feedback", daemon=True)
        self._thread.start()

    def play(self, name, count=1, interval=0.0, source="action"):
        path = {
            "generic": "./Sounds/System/0/generic.mp3",
            "volume_up": "./Sounds/System/0/vol-up.mp3",
            "volume_down": "./Sounds/System/0/vol-down.mp3",
        }.get(name)
        if path is None:
            print("FEEDBACK rejected name=%s reason=unknown" % name, flush=True)
            return False
        try:
            enqueued_at = time.monotonic()
            self._requests.put_nowait((name, path, count, interval,
                                       enqueued_at, source))
            print("FEEDBACK enqueue name=%s source=%s uptime=%.6f count=%d "
                  "depth=%d" %
                  (name, source, enqueued_at, count,
                   self._requests.qsize()), flush=True)
            return True
        except queue.Full:
            print("FEEDBACK drop name=%s reason=queue_full" % name, flush=True)
            return False

    def _run(self):
        while not self._stop.is_set():
            try:
                request = self._requests.get(timeout=0.1)
            except queue.Empty:
                continue
            if request is None:
                self._requests.task_done()
                break
            name, path, count, interval, enqueued_at, source = request
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
            finally:
                self._requests.task_done()

    def close(self):
        self._stop.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
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
        # GPIO supplies only the channel number; map it without touching the
        # active player.  The owner thread performs the actual button action.
        try:
            button = cls.inputs.index(channel)
        except ValueError:
            return
        if cls.input_dispatcher is not None:
            cls.input_dispatcher("generic", button)

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
