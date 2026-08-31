# Application architecture

## Scope and evidence

This document describes commit `e099e45` (`v1.0`, 2026-03-24). **Verified** statements are derived from tracked source, scripts, or documentation. **Inference** statements explain likely runtime effects and must be confirmed on the Raspberry Pi.

## Shape of the application

**Verified:** The application is a single Python process launched through `RasPlayer.py`. It has no package metadata, configuration file, database, network server, or persistent application state. Mode, selected item/set, volume, and playback state live in process memory.

`RasPlayer.py` creates a shared libVLC instance lazily and a dedicated media-player object for each prepared mode. It configures GPIO, launches the startup MP3 with mpg123, registers process-owned GPIO callbacks, and runs an infinite keep-alive loop. A bounded command-owner thread serializes active state and playback calls; slow mode construction/teardown runs on generation-checked workers.

```text
system service -> RasPlayer.py
                    |-- RPi.GPIO edge callbacks -> bounded command queue
                    |-- libVLC instance + per-mode players -> files/HTTP radio
                    |-- pygame mixer -> system, animal, and instrument samples
                    |-- FluidSynth -> distance-controlled synth
                    `-- 50 ms main loop -> active SynthPlayer.update()
```

## Startup flow

**Verified:** The current startup path is deliberately split at `LOCAL_READY`:

1. Record a monotonic `python_entry` marker and import only GPIO, pygame/sample support, and standard-library control code. VLC, mode classes, FluidSynth, and asyncio are not imported here.
2. Register signal handlers, select BCM numbering, configure fixed GPIO pins, and emit `gpio_ready`.
3. Set mixer volume with `amixer -c 0 sset PCM <volume>%` (initially 80%). Launch `mpg123` for `TurnOn.mp3` and verify it remains running; pygame is not imported on this path.
4. Register rising-edge events for global controls and mode selectors. `LOCAL_READY` means physical controls are registered and the mpg123 startup sound has been successfully triggered. Pygame is loaded on first volume/sample-mode use. No content mode is selected (`PlayerMode.NONE`).
5. On a mode selection, the owner records a generation and starts lazy backend preparation off-thread. The shared VLC instance is created once, each mode receives a dedicated media player, and only the current generation may become active. FluidSynth remains Synth-only.

The markers are concise `STARTUP <name> elapsed=<seconds>` lines using
`time.monotonic()`. Detailed measured cold/warm timings and first-use mode
costs are recorded in `docs/pi-boot-optimization.md`.

### Import and initialization ownership

| Component | Import/initialization point | Required before `LOCAL_READY` |
| --- | --- | --- |
| `RPi.GPIO` | Entry point imports and pin setup | Yes |
| pygame/SDL mixer | Lazy `SamplePlayer` import on volume/sample-mode use | No |
| VLC/libVLC | `ensure_vlc()` called by a selected non-system mode | No |
| Mode classes | Background mode-preparation worker | No |
| FluidSynth | `SynthPlayer.__init__` on preparation worker | No |
| queue/threading | Music mode constructor/event callback | No |

**Verified:** Relative media paths are resolved from the working directory. The documented service uses `/home/dnl/RasPlayer`, so a deployment must retain that directory structure and the `Sounds` tree.

## Modes and state

| Mode | Selector (BCM) | Implementation | Startup behavior | Playback path |
| --- | ---: | --- | --- | --- |
| Music | 24 | `MusicPlayer` | waits one second, loads `Sounds/Music/01/*.mp3`, starts first track | libVLC/ALSA |
| Animals | no dedicated selector in current source | `SamplePlayer(...Animals, 3)` | preloads `Animals/0/*.mp3`; plays a short sample pattern | pygame/SDL mixer |
| Instrument samples | 25 | `SamplePlayer(...Instruments, 5)` | preloads `Instruments/0/*.mp3`; plays a short sample pattern | pygame/SDL mixer |
| Online radio | 10 | `OnlinePlayer` | immediately starts the first HTTP station and monitors VLC state/timeout | libVLC/ALSA + network |
| Synth | 9 | `SynthPlayer` | starts FluidSynth ALSA driver and loads a system soundfont | FluidSynth/ALSA |
| None | n/a | no active player | only startup/system sounds are available | pygame for system sound |

**Verified from current source:** `setPlayerMode()` ignores an already-active request, detaches the active object, and delegates teardown and construction without sleeping on the owner. Completion carries a generation token; stale results are cleaned up and cannot replace a newer selection. Initialization exceptions include tracebacks and leave the current generation in `FAILED`/`NONE`. Dedicated VLC players isolate a slow Online teardown from a new local Music player.

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

**Verified:** Global controls have 500 ms software bounce times; mode selectors use 1,000 ms and generic buttons use 190 ms. Generic GPIO callbacks are registered once by `RasPlayer.py` and only enqueue a button index. The owner dispatches to the currently active mode. Synth handles the resulting command directly: it selects the instrument, logs the current distance gate, and issues `noteon()` with a short event latch so a valid rising-edge command cannot disappear before the next level poll. Commands received while a mode is still initializing are explicitly logged as skipped.

**Verified from source:** Synth owns a dedicated ultrasonic worker. It accesses
`/dev/gpiomem` through the same GPIO register path as the privileged hardware
diagnostic, sends a 10 microsecond trigger, applies 30 ms bounds to both echo
edges, and waits 100 ms after each measurement—the intentional playable
cadence from historical commit `5d73c6e`. The serialized command-owner
tick only reads the latest sample. Timeouts and invalid samples are
rate-limited; only distances in the 5–35 cm Synth control range can drive a
note. Valid control distance is quantized into the historical 2 cm/half-tone
steps; invalid samples retain rather than replace the last valid step.

**Open question:** The exact ultrasonic module, voltage-level conversion on the echo line, pull-down/up circuitry, LED circuit, audio adapter/DAC, amplifier, and button wiring are not identified in the repository. The trigger/echo naming is consistent with an HC-SR04-style sensor, but that is an inference only.

## Audio and media

**Verified:** There are three independent audio clients:

- `python-vlc` uses one instance with dedicated per-mode players. Online applies 1 s network caching/reconnect options and logs open return, state changes, failures and an 8 s timeout.
- `pygame.mixer` plays startup, volume, animal, and instrument MP3 samples. It is initialized once on first use at 44.1 kHz, signed 16-bit stereo, and a 4096-frame buffer.
- `pyfluidsynth` starts its own ALSA driver with period size 1024, four periods, and polyphony 64. It loads `/usr/share/sounds/sf2/FluidR3_GM.sf2` and changes GM programs using the generic buttons.

**Verified:** The repository currently contains roughly 305 MB of MP3 content and about 1.35 MB of WAV content. Sample paths are selected by glob and lexical sort; ordering therefore depends on filenames. `Sounds/` is ignored for new Git additions, though the existing asset files are currently tracked. `syncSoundsToPi.sh` separately rsyncs `Sounds` to the target.

**Verified:** VLC end callbacks enqueue `next`; they do not directly call the active player.

## Concurrency and process interaction

**Verified:** GPIO and VLC callbacks enqueue timestamped commands. One daemon owner serializes active state, player calls, generation acceptance and `update()`; preparation/cleanup workers never directly replace active state. The Synth ultrasonic worker publishes only its latest measured distance under a lock and never mutates active mode ownership. Handler failures are isolated. See `docs/stability-and-event-model.md`.

## Test coverage and history

**Verified:** The only tracked test utility is `tests/underrun_test.py`. It plays a supplied WAV with pygame and can spawn `journalctl -f` to print lines containing `underrun`; it is a manual device diagnostic, not an automated regression test.

**Verified:** History shows the project moved from `mpyg321` to VLC in January 2026, added pygame underrun buffering in December 2025, and replaced a PyAudio/numpy oscillator with FluidSynth in March 2026. The current ultrasonic polling timeouts were added in the latest commit. No history contains a reproducible operating-system configuration or dependency lockfile.
