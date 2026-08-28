# Existing Raspberry Pi baseline

## Scope and evidence

This baseline was collected on 2026-08-28 over SSH from `dnl@192.168.0.70` using read-only commands. The Pi was not rebooted, reconfigured, or updated. No SD card was accessed from the development PC.

Labels used here:

- **Pi-verified:** directly observed on the running Pi.
- **Repository-verified:** observed in the checked-out repository at `e099e45` (`v1.0`).
- **Inference:** interpretation that requires a controlled test or physical inspection.

Monotonic kernel/journal timestamps are used for boot timing. **Inference:** Wall-clock timestamps around boot are inconsistent with uptime, most likely because network time corrected an initially inaccurate clock; they are not suitable for duration calculations.

## Executive findings

1. **Pi-verified:** This is a Raspberry Pi 3 Model B Plus Rev 1.4, revision code `a020d4`, running 64-bit Debian 11.9 (Bullseye) with Raspberry Pi kernel `6.1.21-v8+` on AArch64.
2. **Pi-verified:** Linux reports 30.028 seconds from kernel entry through completed userspace startup. RasPlayer is spawned at kernel time 29.909 seconds and reaches its last startup log before playing the startup sound at approximately 37.001 seconds.
3. **Pi-verified:** `NetworkManager-wait-online.service` is the largest boot delay at 17.012 seconds. Wi-Fi has one rejected association before connecting; local RasPlayer startup is unnecessarily ordered after `multi-user.target` and therefore after this network-online path.
4. **Pi-verified:** RasPlayer itself needs about 7.1 seconds from process spawn to its loaded-system-sample state. Eager imports of pygame/SDL, VLC, numpy, FluidSynth bindings, and GPIO happen before controls become usable.
5. **Pi-verified:** `vcgencmd get_throttled` returned `0x50005` twice, and the kernel logged `Undervoltage detected!`. This means under-voltage and throttling were both active and had occurred earlier in the boot. Performance measurements and stability conclusions are compromised until power is corrected.
6. **Pi-verified:** A custom `wifi-failover.service` is failing and restarting continuously. It had restarted 90 times after roughly 34 minutes of uptime. It does not explain the initial 17-second wait, but it creates continuous runtime process/log churn.
7. **Pi-verified + repository-verified:** SHA-256 hashes for all six deployed Python modules exactly match the repository. The baseline therefore describes the checked-in application, not a divergent copy.

## Hardware, OS, kernel, and firmware

| Item | Pi-verified value |
| --- | --- |
| Model | Raspberry Pi 3 Model B Plus Rev 1.4 |
| Revision code | `a020d4` |
| Architecture | `arm64`, 64-bit userspace, AArch64 kernel |
| OS | Debian GNU/Linux 11 (Bullseye), `/etc/debian_version` = `11.9` |
| Kernel | `6.1.21-v8+ #1642 SMP PREEMPT`, built 2023-04-03 |
| VideoCore firmware | build timestamp 2023-03-17; version `82f3750a65fadae9a38077e3c2e217ad158c8d54` |
| `/boot/.firmware_revision` | `80c9a5f08cad3d0e27b5205f5a0979d50af2c4d7` |
| Temperature snapshot | 47.2 degrees C |
| Power/throttle snapshot | `0x50005`; current and historical under-voltage and throttling |

**Pi-verified:** The kernel logs the BCM2835 watchdog driver at 3.217 seconds and exposes `/dev/watchdog` and `/dev/watchdog0`. Raspberry Pi names this driver family BCM2835 even on the BCM2837B0-based Pi 3B+. No watchdog userspace service is installed or active, and the device is not currently being serviced. The device nodes are root-only (`0600`). Kernel config files were not available under `/proc/config.gz` or `/boot/config-*`, but the live device and driver log prove runtime support.

The `0x50005` interpretation follows the [official Raspberry Pi `vcgencmd get_throttled` bit table](https://www.raspberrypi.com/documentation/computers/os.html#vcgencmd). This is a high-priority physical power-supply/cable/load issue, not an OS-migration detail.

## Boot configuration

**Pi-verified:** This Bullseye image uses `/boot/config.txt` and `/boot/cmdline.txt`; `/boot/firmware/config.txt` and `/boot/firmware/cmdline.txt` do not exist.

Relevant `/boot/config.txt` settings:

- onboard audio enabled: `dtparam=audio=on`;
- camera and DSI display auto-detection enabled;
- full KMS graphics enabled: `dtoverlay=vc4-kms-v3d`, two framebuffers;
- 64-bit mode enabled: `arm_64bit=1`;
- no `disable-bt` overlay and no watchdog parameter in this file;
- default display-oriented settings remain even though the appliance is described as headless.

Relevant kernel command-line behavior:

- serial and local consoles are enabled (`console=serial0,115200`/effective `ttyS0` and `console=tty1`);
- root is ext4 on the second SD partition with `rootwait` and `fsck.repair=yes`;
- Wi-Fi regulatory domain is Austria (`AT`);
- effective firmware arguments enable onboard headphones, disable HDMI audio, and select composite video.

**Pi-verified:** The default systemd target is `multi-user.target`. Bluetooth remains enabled as a service, although it was inactive at inspection time. This contradicts repository README notes suggesting that Bluetooth was disabled.

## Measured boot timeline

`systemd-analyze` reported:

```text
Startup finished in 4.147s (kernel) + 25.880s (userspace) = 30.028s
multi-user.target reached after 25.729s in userspace
```

The unit times from `systemd-analyze critical-chain` are userspace-relative; the journal times below are kernel-monotonic and therefore include the 4.147-second kernel phase.

| Kernel-monotonic time | Event | Interpretation |
| ---: | --- | --- |
| 0.000 s | Linux kernel timing begins | Firmware/bootloader time occurred before this and is not measured by Linux. |
| 3.217 s | BCM2835 watchdog driver detected | Hardware watchdog becomes available during kernel initialization. |
| 4.147 s | Kernel phase complete / userspace phase begins | From `systemd-analyze`. |
| 9.533 s | Local filesystems reached | Root and boot filesystems are available. |
| 10.769 s | Basic system reached | General services begin starting. |
| 11.622 s | wpa_supplicant starting | Wi-Fi userspace begins. |
| 11.887–12.700 s | NetworkManager starts | Network target is then considered reached. |
| 12.743 s | NetworkManager wait-online starts | Critical boot wait begins. |
| 17.327 s | Wi-Fi connection activation begins | Active profile is DHCP-based. |
| 23.414 s | First association rejected | This extends the boot wait. |
| 28.818 s | Wi-Fi association succeeds | Link connects. |
| 29.764 s | `network-online.target` reached | Wait-online consumed 17.012 seconds. |
| 29.878 s | `multi-user.target` reached | RasPlayer is explicitly ordered after this target. |
| 29.913 s | systemd reports RasPlayer started | `/usr/bin/python` has been spawned. |
| 35.703 s | first Python line: pygame version | About 5.79 seconds spent importing before this output. |
| 36.929 s | application sets volume | `amixer` is invoked. |
| 37.001 s | system sample list loaded | Closest log proxy for startup sound/control readiness. |

**Inference:** Actual audible startup and first accepted button were not captured by an external probe. The code plays the startup sample and registers callbacks immediately after the 37.001-second log, so approximately 37 seconds after kernel timing begins is the best available readiness proxy.

**Open question:** Firmware/bootloader duration from power application to Linux timestamp zero cannot be recovered from this running boot. The reported physical observation of roughly 45 seconds is compatible with the measured 37-second Linux/application path plus an unmeasured firmware interval, power-on hardware initialization, and human/audio observation latency, but that remainder is not verified.

## Ranked boot contributors

Durations overlap; `systemd-analyze blame` entries must not be added together. Ranking is based on the critical path and application log deltas.

1. **Networking: 17.012 s.** `NetworkManager-wait-online.service` starts at kernel time 12.743 seconds and finishes at 29.756/29.764 seconds. Wi-Fi association is rejected once before succeeding. This delays `network-online.target`, `rc-local`, `multi-user.target`, and consequently RasPlayer.
2. **RasPlayer startup: approximately 7.09 s.** Process spawn at 29.909/29.913 seconds to loaded system samples at 37.001 seconds. Import time dominates the first 5.79 seconds. Current CPU throttling may inflate this result.
3. **Other systemd/userspace: 8.868 s outside wait-online.** Total userspace is 25.880 seconds; subtracting the 17.012-second wait gives an approximate non-network envelope. Much of it is parallel. Notable `blame` durations include `raspi-config` 2.070 s, `e2scrub_reap` 2.035 s, user manager 1.216 s, Avahi 1.105 s, polkit 1.082 s, rng-tools 1.027 s, rfkill 1.009 s, udev trigger 959 ms, ModemManager 805 ms, networking 770 ms, timesyncd 770 ms, journal flush 764 ms, rsyslog 703 ms, and the Pi EEPROM update check 570 ms.
4. **Kernel/device initialization: 4.147 s.** This includes SD/root discovery and drivers. The root block device itself accounts for 2.625 seconds in `blame`, but device timings overlap the kernel/userspace boundary and are not directly additive.
5. **Firmware/bootloader: unknown.** Firmware versions are known, but there is no measured power-on-to-kernel timestamp.

**Inference:** Enabled services with questionable appliance value include ModemManager, Avahi, Bluetooth, udisks2, rsync, display backlight, EEPROM update checking, triggerhappy, rsyslog, and multiple simultaneous network-management components. This is an inventory, not authorization to disable them.

## Exact RasPlayer service and process

**Pi-verified:** `/etc/systemd/system/rasplayer.service` is enabled and contains:

```ini
[Unit]
Description=mp3 player and web radio
After=multi-user.target

[Service]
Type=simple
Restart=always
ExecStart=/usr/bin/python /home/dnl/RasPlayer/RasPlayer.py
WorkingDirectory=/home/dnl/RasPlayer
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Additional live service facts:

- `/usr/bin/python` resolves to Python 3.9.2 (`/usr/bin/python3.9`).
- No `User=` or `Group=` is set, so process PID 520 runs as root.
- systemd's live restart delay is 100 ms; current-boot `NRestarts=0` and the process is running.
- Snapshot process footprint: five threads, 56,232 KiB RSS, 373,624 KiB virtual memory, and 12% lifetime CPU at the time sampled.
- The player has `/dev/snd/pcmC0D0p` open, confirming playback through card 0.

**Pi-verified:** Every application module and the `Sounds` directory is mode `0777`, owned by `dnl:dnl`. `__pycache__` is root-owned. World-writable executable source is a reliability/security defect to avoid in the immutable image.

**Pi-verified + repository-verified:** Remote/local SHA-256 values match for `RasPlayer.py`, `MusicPlayer.py`, `OnlinePlayer.py`, `SamplePlayer.py`, `SoundPlayer.py`, and `SynthPlayer.py`. The deployed directory is 293 MiB, `Sounds` is 293 MiB with 91 files, and the media footprint agrees with the repository inventory.

## Actual runtime dependencies

The root service sees the following runtime, which differs from the `dnl` login user's pip environment for numpy. Locations matter because the installation is not reproducible from apt alone.

| Component | Version used by root-run service | Source/location |
| --- | --- | --- |
| Python | 3.9.2 | Debian `/usr/bin/python3.9` |
| python-vlc | 3.0.21203 | `/usr/local/lib/python3.9/dist-packages/vlc.py` |
| pygame | 2.6.1 | `/usr/local/lib/python3.9/dist-packages`; reports SDL 2.28.4 and SDL_mixer 2.6.3 |
| numpy | 1.19.5 | Debian `/usr/lib/python3/dist-packages` |
| pyfluidsynth | module corresponding to installed 1.3.4 | `/usr/local/lib/python3.9/dist-packages/fluidsynth.py` |
| RPi.GPIO | 0.7.1 | `/usr/local/lib/python3.9/dist-packages` |
| libVLC | 3.0.21 | Debian/Raspberry Pi package, AArch64 |
| FluidSynth | 2.1.7 / `libfluidsynth.so.2` | Debian package |
| ALSA userspace | 1.2.4 | Debian/Raspberry Pi packages |
| mpg123 | 1.26.4 | Debian package/library |
| FluidR3 GM soundfont | package 3.1-5.2 | `/usr/share/sounds/sf2/FluidR3_GM.sf2` |

**Pi-verified:** The login user has numpy 2.0.2 and several bindings under `/home/dnl/.local`, but the root service does not use that numpy. The image build must reproduce the root service's imports, not merely `pip list` from `dnl`.

## Audio baseline

ALSA cards:

| Card | Device | Live role |
| ---: | --- | --- |
| 0 | `bcm2835 Headphones` | Current RasPlayer playback; application and `/etc/asound.conf` select card 0. |
| 1 | `GHW-136D-20231007 USB Audio` | USB playback and capture device present; not the current player PCM. |
| 2 | `vc4-hdmi` | HDMI PCM present, though effective firmware arguments disable HDMI audio. |

`/etc/asound.conf` defines an asymmetric default and routes playback/control to hardware card 0. No `/home/dnl/.asoundrc` exists. Card 0 exposes the expected `PCM` switch and volume; the switch was on and the sampled raw volume was `-1728` (-17.28 dB). The repository's `amixer -c 0 sset PCM ...` assumption is therefore correct for this hardware state.

Loaded audio modules include `snd_bcm2835`, `snd_usb_audio`, `snd_usbmidi_lib`, `snd_soc_hdmi_codec`, and the normal ALSA PCM/timer/core modules. The Buildroot baseline should initially preserve onboard analog, USB Audio, and HDMI-related kernel support until the physical USB device and intended output path are confirmed.

Historical RasPlayer logs show:

- repeated online-radio DNS and HTTP failures on 2026-08-27;
- VLC `cannot pre fill buffer` and demux errors;
- FluidSynth warnings that SDL2 was not initialized (the synth explicitly requests ALSA, so the practical effect still needs testing);
- no `underrun` string in the retained RasPlayer journal count;
- many callback tracebacks when next/previous is pressed before a mode is selected: `soundPlayer` is `None`, producing `AttributeError`. These exceptions occur in GPIO callback context and did not terminate the main process in the captured sequence.

The retained RasPlayer journal contains 235 `Traceback` markers and 90 `Main process exited` markers across its history. These are raw log-line counts, not necessarily distinct root causes. The current boot has no RasPlayer restart (`NRestarts=0`); detailed attribution of all historical process exits remains open.

## GPIO and watchdog baseline

- `/dev/gpiomem` exists as `root:gpio` mode `0660`; `/dev/mem` is `root:kmem` mode `0640`.
- User `dnl` belongs to `gpio`, `audio`, `input`, `spi`, `i2c`, and other standard Pi groups, but the current service bypasses those permissions by running as root.
- RPi.GPIO 0.7.1 is the module loaded by the service.
- `raspi-gpio` is installed; physical wiring and electrical protection remain unverified.
- The BCM2835 hardware watchdog device exists, is inactive, and has no watchdog service. This confirms the Buildroot watchdog design is feasible but not currently implemented.

## Networking baseline

**Pi-verified:** Active Wi-Fi is managed by NetworkManager, not dhcpcd:

- `wlan0` is connected with DHCP address `192.168.0.70/24`, gateway and DNS at `192.168.0.1`;
- IPv6 addresses are also present;
- NetworkManager 1.30.6, `wpa_supplicant`, legacy `networking.service`, and `NetworkManager-wait-online` are enabled;
- `dhcpcd.service` is disabled and inactive;
- `/etc/dhcpcd.conf` still contains stale static entries for `192.168.0.251` on Wi-Fi and `192.168.0.252` on Ethernet plus `ipv4only/noipv6`, but these settings are not controlling the active NetworkManager DHCP connection;
- DNS resolution for both currently referenced radio hostnames succeeded during inspection.

This directly contradicts repository documentation that presents dhcpcd/static `192.168.0.251` as current. Deployment scripts using `192.168.0.70` match the live address.

`wifi-failover.service` is enabled, ordered after and wants `network-online.target`, and runs `/usr/local/bin/wifi-failover.sh` with `Restart=always`/10-second delay. It repeatedly exits with status 10 and restarts. Its script content was intentionally not copied because network scripts may contain credentials; only the unit and process metadata were inspected.

## Storage, mounts, and memory

| Item | Pi-verified value |
| --- | --- |
| SD device | `mmcblk0`, nominal 64 GB (`SN64G`, 59.5 GiB visible) |
| Boot partition | 256 MiB FAT32, mounted read-write at `/boot`, 25% used |
| Root partition | 59.2 GiB ext4, mounted read-write with `noatime`, 4.0 GiB used / 52 GiB available |
| Swap | none |
| RAM | 909 MiB usable; 112 MiB used and 741 MiB available at snapshot |
| Volatile mounts | `/run`, `/dev/shm`, `/run/lock`, and per-user runtime tmpfs |

The current writable root and boot filesystems contrast with the planned read-only Buildroot appliance. No application state was found that requires the root filesystem to remain writable.

## Consequences for the Buildroot plan

1. **Power must be corrected before benchmarking.** Current under-voltage and throttling may explain intermittent instability and inflate both kernel and application timing. A new OS cannot compensate for inadequate power.
2. **The unchanged application has a measured 7.1-second startup cost.** A complete 3–5 second power-to-controls target is not credible without later lazy imports/startup restructuring, native/backend simplification, or another measured way to remove most of that cost. Buildroot alone removes the 17-second network wait but cannot erase Python import time.
3. **Revise the first-image expectation.** With the current application retained, 8–12 seconds from power to local readiness is a more defensible initial Buildroot target on healthy power; 3–5 seconds remains a later optimization target.
4. **Preserve more audio support initially.** The actual system has onboard analog, USB Audio playback/capture, and HDMI PCM. Do not prune USB/HDMI drivers until the attached USB device and appliance output requirements are confirmed.
5. **Reproduce root-visible module versions.** The current pip/apt mixture is inconsistent between root and `dnl`. Buildroot recipes should pin the root service versions listed above and validate pygame's SDL/SDL_mixer behavior.
6. **Networking must be outside the local critical path.** The measured 17-second association wait validates the existing plan to start local playback independently and bring Wi-Fi up asynchronously.
7. **Hardware watchdog support is already proven.** The Buildroot design can use the BCM2835 watchdog device, but needs an explicit health-aware userspace owner.
8. **The immutable filesystem recommendation is strengthened.** World-writable production source and media should become root-owned/read-only image content.

## Remaining unknowns

- Power supply rating/quality, USB cable gauge/length, amplifier/USB load, and whether the under-voltage condition persists after physical remediation.
- Firmware/bootloader duration from power-on to Linux timestamp zero; requires an external power/LED/GPIO/serial measurement or instrumented cold boot.
- Exact audible-startup and first-button-ready timestamps; current logs provide only a close software proxy.
- Function of the attached `GHW-136D-20231007 USB Audio` device and whether playback, microphone/capture, HDMI, composite video, camera/display auto-detection, Bluetooth, UART console, Ethernet, or other peripherals must be retained.
- Physical GPIO/button/LED/sensor wiring, ultrasonic sensor type, and 5 V-to-3.3 V echo protection.
- Root causes for all 90 historical RasPlayer process-exit log entries and whether any correspond to reported hangs.
- Contents/intended behavior of the credential-sensitive Wi-Fi failover script and whether AP fallback is a release requirement.
- Desired persistent logging, content-update, remote-recovery, and field-update policies.
