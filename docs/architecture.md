# Application architecture

## Scope and evidence

This document describes commit `e099e45` (`v1.0`, 2026-03-24). **Verified** statements are derived from tracked source, scripts, or documentation. **Inference** statements explain likely runtime effects and must be confirmed on the Raspberry Pi.

## Shape of the application

**Verified:** The application is a single Python process launched through `RasPlayer.py`. It has no package metadata, configuration file, database, network server, or persistent application state. Mode, selected item/set, volume, and playback state live in process memory.

`RasPlayer.py` creates the shared libVLC instance and media-player object lazily when the first non-system mode is selected. It configures GPIO, plays a pygame startup sound, registers GPIO edge callbacks, and runs an infinite keep-alive loop. A bounded command-owner thread serializes input/mode work and calls the active mode's `update()` at roughly 50 ms intervals.

```text
system service -> RasPlayer.py
                    |-- RPi.GPIO edge callbacks -> bounded command queue
                    |-- libVLC shared player -> music files or HTTP radio
                    |-- pygame mixer -> system, animal, and instrument samples
                    |-- FluidSynth -> distance-controlled synth
                    `-- 50 ms main loop -> active SynthPlayer.update()
```

## Startup flow

**Verified:** The current startup path is deliberately split at `LOCAL_READY`:

1. Record a monotonic `python_entry` marker and import only GPIO, pygame/sample support, and standard-library control code. VLC, mode classes, FluidSynth, numpy, and asyncio are not imported here.
2. Register signal handlers, select BCM numbering, configure fixed GPIO pins, and emit `gpio_ready`.
3. Set mixer volume with `amixer -c 0 sset PCM <volume>%` (initially 80%). Construct the system `SamplePlayer`, initialize pygame mixer, preload its three MP3 files, and play item 0 (expected `TurnOn.mp3`).
4. Register rising-edge events for global controls and mode selectors. `LOCAL_READY` means physical controls are registered and the immediate local system-sound response can be produced. No content mode is selected (`PlayerMode.NONE`).
5. On the first mode selection, import and initialize only that mode's dependencies. The shared VLC instance is created once on first non-system mode use; FluidSynth and numpy are loaded only for Synth mode.

The markers are concise `STARTUP <name> elapsed=<seconds>` lines using
`time.monotonic()`. Detailed measured cold/warm timings and first-use mode
costs are recorded in `docs/pi-boot-optimization.md`.

### Import and initialization ownership

| Component | Import/initialization point | Required before `LOCAL_READY` |
| --- | --- | --- |
| `RPi.GPIO` | Entry point imports and pin setup | Yes |
| pygame/SDL mixer | `SamplePlayer` import and system-sample construction | Yes, for startup audio |
| VLC/libVLC | `ensure_vlc()` called by a selected non-system mode | No |
| Music/Online player classes | Inside `setPlayerMode()` | No |
| FluidSynth | Inside `SynthPlayer.__init__` | No |
| numpy | Inside `SynthPlayer.freq_to_midi()` | No |
| queue/threading | Music mode constructor/event callback | No |

**Verified:** Relative media paths are resolved from the working directory. The documented service uses `/home/dnl/RasPlayer`, so a deployment must retain that directory structure and the `Sounds` tree.

## Modes and state

| Mode | Selector (BCM) | Implementation | Startup behavior | Playback path |
| --- | ---: | --- | --- | --- |
| Music | 24 | `MusicPlayer` | waits one second, loads `Sounds/Music/01/*.mp3`, starts first track | libVLC/ALSA |
| Animals | no dedicated selector in current source | `SamplePlayer(...Animals, 3)` | preloads `Animals/0/*.mp3`; plays a short sample pattern | pygame/SDL mixer |
| Instrument samples | 25 | `SamplePlayer(...Instruments, 5)` | preloads `Instruments/0/*.mp3`; plays a short sample pattern | pygame/SDL mixer |
| Online radio | 10 | `OnlinePlayer` | waits one second, starts the first hard-coded HTTP station | libVLC/ALSA + network |
| Synth | 9 | `SynthPlayer` | starts FluidSynth ALSA driver and loads a system soundfont | FluidSynth/ALSA |
| None | n/a | no active player | only startup/system sounds are available | pygame for system sound |

**Verified:** `setPlayerMode()` ignores a request for the already active enum value. When replacing a non-null mode object it calls `soundPlayer.player.stop()`, sets `is_playing` false, and sleeps 200 ms before creating the next object. Each player object shares the same VLC player, which is now created once on first non-system mode use. If optional mode initialization raises, the exception is logged, the mode returns to `NONE`, and the local control loop remains alive. `SynthPlayer` also defines `stop()`, but the mode-switch code does not call it.

**Verified:** `nextPlayerMode()` and `inputModeChange()` are present but the corresponding GPIO event is commented out. The selector for animal mode is also commented out. `nextPlayerMode()` sets `playerMode` before calling `setPlayerMode()`, making that call a no-op; this dead path is not part of the enabled controls.

## Input and hardware interface

**Verified:** GPIO uses `RPi.GPIO` and BCM numbering. All buttons use rising-edge detection and `GPIO.PUD_DOWN`; no hardware debounce circuit is documented. `GPIO-Mapping.md` is the authoritative in-repository mapping:

| Function | BCM | Header pin |
| --- | ---: | ---: |
| Play/pause | 4 | 7 |
| Ultrasonic trigger / echo | 14 / 15 | 8 / 10 |
| Next / previous | 17 / 27 | 11 / 13 |
| Volume up / down | 22 / 23 | 15 / 16 |
| Music / online / synth mode | 24 / 10 / 9 | 18 / 19 / 21 |
| Instrument-sample mode | 25 | 22 |
| Five generic buttons | 11, 5, 6, 19, 16 | 23, 29, 31, 35, 36 |
| Status LED output | 26 | 37 |

**Verified:** Global controls have 500 ms software bounce times; mode selectors use 1,000 ms. Generic buttons use 190 ms (400 ms in `MusicPlayer`, which re-registers them). The base-class event registrations dispatch to the active subclass's `buttonDown()` method: generic buttons select playlists in Music mode, samples/instruments in sample modes, radio stations in Online mode, and synth instruments in Synth mode. The commented registrations in `OnlinePlayer` would have been redundant.

**Verified:** The ultrasonic routine sends a 10 microsecond trigger pulse and polls echo. It has a 50 ms start timeout and a 20 ms end timeout, added in the latest commit. It returns a calculated distance even when either timeout expires.

**Open question:** The exact ultrasonic module, voltage-level conversion on the echo line, pull-down/up circuitry, LED circuit, audio adapter/DAC, amplifier, and button wiring are not identified in the repository. The trigger/echo naming is consistent with an HC-SR04-style sensor, but that is an inference only.

## Audio and media

**Verified:** There are three independent audio clients:

- `python-vlc` with `vlc.Instance("--aout=alsa")` plays music and five hard-coded HTTP radio URLs.
- `pygame.mixer` plays startup, volume, animal, and instrument MP3 samples. It is initialized once on first use at 44.1 kHz, signed 16-bit stereo, and a 4096-frame buffer.
- `pyfluidsynth` starts its own ALSA driver with period size 1024, four periods, and polyphony 64. It loads `/usr/share/sounds/sf2/FluidR3_GM.sf2` and changes GM programs using the generic buttons.

**Verified:** The repository currently contains roughly 305 MB of MP3 content and about 1.35 MB of WAV content. Sample paths are selected by glob and lexical sort; ordering therefore depends on filenames. `Sounds/` is ignored for new Git additions, though the existing asset files are currently tracked. `syncSoundsToPi.sh` separately rsyncs `Sounds` to the target.

**Verified:** VLC automatically advances music on `MediaPlayerEndReached` by creating a daemon thread that calls `MusicPlayer.playNext()`. No other use of the imported `queue` exists.

## Concurrency and process interaction

**Verified:** GPIO and VLC callbacks now enqueue commands into a bounded queue. One daemon owner thread serializes mode changes, player calls, teardown, and `update()`, while the main thread remains a keep-alive loop. Handler failures are isolated. See `docs/stability-and-event-model.md` for lifecycle details.

**Inference:** `RPi.GPIO` callback execution and VLC event callbacks can overlap each other and the main loop. Because all mutate global `soundPlayer`, shared VLC state, GPIO event registrations, and (for mode changes) audio initialization without synchronization, rapid or coincident input can produce races, stale callbacks, or partially completed transitions.

## Test coverage and history

**Verified:** The only tracked test utility is `tests/underrun_test.py`. It plays a supplied WAV with pygame and can spawn `journalctl -f` to print lines containing `underrun`; it is a manual device diagnostic, not an automated regression test.

**Verified:** History shows the project moved from `mpyg321` to VLC in January 2026, added pygame underrun buffering in December 2025, and replaced a PyAudio/numpy oscillator with FluidSynth in March 2026. The current ultrasonic polling timeouts were added in the latest commit. No history contains a reproducible operating-system configuration or dependency lockfile.
