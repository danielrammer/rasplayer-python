# Operations, stability observations, and minimal-Linux migration

## Evidence convention

**Verified** is supported by tracked repository material at `v1.0` (`e099e45`). **Inference** is a risk assessment, not a confirmed field failure. **Open question** needs information from the target Pi or its OS image.

The running installation was inspected on 2026-08-28. Its verified configuration and measurements supersede older README assumptions; see `docs/existing-pi-baseline.md`.

## Current deployment and launch

**Verified:** `readme.md` documents a headless Raspberry Pi OS deployment and this systemd unit (the unit file itself is not tracked):

```ini
[Unit]
Description=mp3 player and web radio
After=multi-user.target
[Service]
Type=simple
Restart=always
ExecStart=/usr/bin/python /home/dnl/RasPlayer/RasPlayer.py
WorkingDirectory=/home/dnl/RasPlayer
[Install]
WantedBy=multi-user.target
```

**Verified from repository:** The documented target user and default deployment IP are `dnl` and `192.168.0.70`. `copyScripts.sh` rsyncs the Python files; `syncSoundsToPi.sh` rsyncs the media tree; `restartPlayer.sh` runs `sudo systemctl restart rasplayer.service` through SSH. The README also describes a static Wi-Fi address of `192.168.0.251`.

**Verified from running Pi (2026-08-28):** NetworkManager DHCP supplies the live `192.168.0.70` address. dhcpcd is disabled; the static `.251` entry remains only in an inactive/stale dhcpcd configuration.

**Verified:** The README says `mpg123`, Python/pip, `mpyg321`, and pygame were installed at different points. Current source instead imports `vlc`, `RPi.GPIO`, `pygame`, `numpy`, and `fluidsynth`, and invokes `amixer`. It assumes ALSA device card 0, PCM mixer control, and the FluidR3 soundfont at `/usr/share/sounds/sf2/FluidR3_GM.sf2`.

**Verified after the mpg123 startup optimization:** The entry point imports
GPIO and standard-library control code before `LOCAL_READY`; mpg123/ALSA plays
the startup MP3, while pygame, VLC, mode classes, FluidSynth, numpy, and
MusicPlayer threading support are loaded only when needed. See
`docs/pi-boot-optimization.md` for Pi measurements.

**Verified:** Historical README boot suggestions include headless operation; keeping `dhcpcd.service`; disabling Bluetooth by `dtoverlay=disable-bt`; disabling `hciuart`; turning off IPv6 in dhcpcd; and disabling `keyboard-setup.service` and `dphys-swapfile.service`. These are notes, not proof that any change is applied to the Pi.

## Stability risks to investigate before changing code

| Risk | Evidence | Consequence / validation needed |
| --- | --- | --- |
| Unsynchronized callbacks and shared mutable state | GPIO callbacks, VLC end thread, and main synth loop all directly call shared player/mode state; no locks/queue | **Inference:** race conditions during button presses or track end can leave playback/mode state inconsistent. Reproduce with button bursts and mode switching while tracks end. |
| Blocking work in callback paths | Mode changes sleep, stop players, glob files, and create/preload MP3 samples; volume calls blocking `subprocess.run(amixer)` | **Inference:** callback delivery can be delayed or fail to keep up; a stuck external/audio call makes controls appear hung. Capture timestamps and stack/process state during failures. |
| No watchdog for live-but-unresponsive process | systemd `Restart=always` restarts exits, but no watchdog is documented; main loop has no health reporting | **Verified/Inference:** crashes restart, but a Python process blocked in a library/system call will remain running and not be recovered automatically. |
| Three concurrent ALSA clients | VLC, pygame mixer, and FluidSynth each use ALSA; mode switch does not invoke `SynthPlayer.stop()` | **Inference:** ALSA device contention or retained FluidSynth workers/resources can cause audio loss, failed mode changes, or accumulated processes. Check `ps`, `lsof`/`fuser`, ALSA logs, and repeated synth transitions. |
| Sensor polling is synchronous | Synth update polls GPIO every loop, with timeouts up to 50 ms + 20 ms | **Verified/Inference:** the latest code prevents unbounded echo waits, but timeout cases can still reduce loop responsiveness and yield a nonzero calculated distance. Measure actual loop duration and sensor fault behavior. |
| Missing/empty media assumptions | Several paths index item 0 or 1 without checking count; music wraps modulo list length | **Verified:** a missing/renamed/empty required media directory can raise an exception and trigger service restart. |
| Limited shutdown cleanup | SIGTERM/SIGINT only call `GPIO.cleanup()` | **Verified/Inference:** VLC, pygame, and FluidSynth are not explicitly stopped/closed by that handler; teardown relies on process exit. |
| Network radio has no app-level timeout/reconnect policy | URLs are plain HTTP and handed directly to VLC | **Inference:** unavailable Wi-Fi/DNS/station endpoint can look like an unresponsive radio mode; behavior is delegated to libVLC. |

The repository does not prove that any of these has caused the reported hang. They are prioritized architectural candidates for the next diagnostic/fix task.

## Buildroot or another minimal-Linux migration

**Verified:** The Python program itself needs no desktop and has no display dependency in active code. Its historical comment mentions `xvfb-run`, but the documented production systemd command runs Python directly. A headless minimal image is therefore compatible in principle.

The following are **verified application requirements** that a target image must provide:

- Raspberry Pi 3B+ compatible kernel/firmware, GPIO userspace support compatible with `RPi.GPIO`, and access permissions for the service user.
- Python 3 plus importable `RPi.GPIO`, `python-vlc`, `pygame`, `numpy`, and `pyfluidsynth` bindings.
- Native libraries/backends for libVLC, SDL/pygame, FluidSynth, ALSA, MP3 decoding, and the codecs/protocol support used for local MP3 and HTTP radio.
- An ALSA card exposed as card 0 with a `PCM` mixer control, or an application/configuration adjustment; `amixer` must be present if current behavior is retained.
- `/usr/share/sounds/sf2/FluidR3_GM.sf2` (or a compatible soundfont at that exact path), unless configuration/code changes later make it selectable.
- The application and its `Sounds/` tree at a working directory compatible with relative paths; roughly 307 MB of current media must fit on persistent storage.
- Wi-Fi driver/firmware, network configuration, DNS, and routing if online-radio mode remains required.

**Verified:** Current launch documentation is systemd-specific. Buildroot commonly uses a smaller init system rather than systemd, so the checked-in unit cannot be used unchanged unless systemd is deliberately included. An init script/service definition must preserve working directory, restart policy, logging, GPIO/audio permissions, and startup ordering.

**Inference:** Full VLC plus Python scientific/audio bindings are likely the principal image-size and build-complexity drivers; startup delay attributed to Linux boot is more likely affected by bootloader/kernel/device/network/service choices than this small Python entry point. This needs an on-device boot trace before selecting a replacement OS or pruning services.

**Inference:** A Buildroot migration may require adapting the application around distribution package availability and runtime data paths, especially for `python-vlc` and `pyfluidsynth`. Treat this as a packaging/integration validation item, not a conclusion that Buildroot is unsuitable.

The concrete phased recommendation, package feasibility review, watchdog design, filesystem layout, and boot target are in `docs/buildroot-migration-plan.md`.

The controlled Raspberry Pi OS optimization and application startup profile are
recorded in `docs/pi-boot-optimization.md`. The selected live service now waits
for `sound.target`/`alsa-restore.service` rather than `multi-user.target`; the
NetworkManager wait helper is masked and the failing AP-failover loop is
disabled. These are reversible Pi-local changes, not application-source
changes.

## Measurements and target-Pi questions

These cannot be determined from the repository:

1. Which Raspberry Pi OS release, kernel, firmware, architecture (32/64-bit), boot medium, filesystem, and boot configuration are actually in use?
2. What do `systemd-analyze critical-chain`, `systemd-analyze blame`, kernel timestamps, and service journal timing show for the reported ~45-second boot? Is “usable” the LED, startup sound, first accepted button, or successful audio?
3. What exact audio hardware is connected (HDMI, analog, USB DAC, I2S HAT, amplifier), which ALSA card/control names it exposes, and are any custom ALSA settings installed?
4. Which exact versions and installation origins are used for Python, libVLC, VLC Python bindings, pygame/SDL, numpy, FluidSynth/pyfluidsynth, RPi.GPIO, codecs, and the soundfont package?
5. What is the actual `/etc/systemd/system/rasplayer.service`, including user/group/environment/dependencies, and which services are enabled or masked?
6. What physical hardware is on every documented GPIO line? In particular, what is the ultrasonic sensor and how is its echo voltage made safe for a 3.3 V GPIO input?
7. What hang symptoms occur, how often, under which input/audio/mode sequence, and does the process remain alive? Relevant evidence: `journalctl -u rasplayer.service`, `dmesg`, under-voltage flags, CPU/RAM, and audio logs.
8. Is Wi-Fi/online radio required at boot or only after local playback is usable? Is static addressing required, and which of the two documented IP addresses is current?
9. Must USB/SSH/rsync development access, automatic network time sync, Bluetooth, or any other peripherals remain in the minimal image?
10. What boot-time target and reliability/recovery behavior are acceptable (read-only root filesystem, watchdog reset, persistent logs, remote update, graceful power loss)?

## Recommended next diagnostic sequence (no code change implied)

1. Capture a clean cold-boot timeline and service journal from the Pi.
2. Record running services, kernel cmdline/configuration, package versions, ALSA topology, and GPIO wiring/power details.
3. Stress mode switches, generic buttons, music end events, radio loss, sensor disconnect, and audio-device failures while collecting logs/process/thread state.
4. Build a minimal proof image only after freezing the required audio/GPIO/network stack and deciding whether systemd remains part of the target.
## Stability refactor status

**Verified from repository:** GPIO/VLC callbacks now enqueue bounded commands handled by one owner thread; mode transitions and FluidSynth/MusicPlayer cleanup are serialized. See `docs/stability-and-event-model.md`.

**Verified 2026-08-28:** The change is deployed to `/home/dnl/RasPlayer`, survived three controlled reboots, and passed remote service/journal checks. Physical button/audio regression checks remain required.

## Watchdog deployment status

**Verified 2026-08-28:** systemd supervises the serialized command-owner heartbeat with a 20-second timeout and bounded restart rate. Forced crash and SIGSTOP hang tests both recovered automatically. The BCM2835 hardware watchdog remains disabled pending a later defense-in-depth review.
