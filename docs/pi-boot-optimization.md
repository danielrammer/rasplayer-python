# Raspberry Pi OS boot optimization results

This document records the controlled, reversible optimization work performed
on `dnl@192.168.0.70` on 2026-08-28. The Pi remained on Raspberry Pi OS
(Debian 11 Bullseye); no application source, package, firmware, or SD-card
content was changed. All timing runs reported `vcgencmd get_throttled=0x50005`
(current and historical under-voltage/throttling), so absolute times are
power-constrained.

## Changes and rollback

The selected OS changes are:

1. `NetworkManager-wait-online.service` is masked. NetworkManager,
   wpa_supplicant, DHCP, DNS, and SSH remain enabled and start asynchronously.
2. `wifi-failover.service` is disabled and stopped. It was an enabled client/AP
   fallback unit that exited status 10 and restarted every 10 seconds while a
   normal NetworkManager Wi-Fi profile was already connected. Its script was
   not copied or exposed; no credentials are recorded here.
3. `/etc/systemd/system/rasplayer.service` was backed up as
   `rasplayer.service.pre-boot-opt-20260828` and replaced by the versioned
   unit in `config/raspberry-pi-os/rasplayer.service`. It starts after
   `local-fs.target` and `sound.target`, with `Wants=sound.target`, and no
   longer has `After=multi-user.target`.

Rollback on the Pi (run as root, after confirming SSH access) is:

```sh
systemctl unmask NetworkManager-wait-online.service
systemctl enable --now NetworkManager-wait-online.service
systemctl enable --now wifi-failover.service
rm -f /etc/systemd/system/rasplayer.service
mv /etc/systemd/system/rasplayer.service.pre-boot-opt-20260828 \
   /etc/systemd/system/rasplayer.service
systemctl daemon-reload
systemctl enable rasplayer.service
systemctl restart rasplayer.service
```

The temporary `/etc/modules-load.d/rasplayer-audio.conf` from iteration 2 was
removed after measurement because it did not move ALSA or player readiness.

## Before and after

The original baseline (with network wait and `After=multi-user.target`) was
4.147 s kernel + 25.880 s userspace = 30.028 s Linux startup. RasPlayer was
spawned at 29.913 s and reached its loaded-system-sample proxy at about
37.001 s after the kernel timeline began. The historical physical observation
was about 45 s.

Immediately before optimization, a representative boot measured 4.202 s
kernel + 19.920 s userspace = 24.122 s; RasPlayer readiness was 31.027 s.
Run-to-run variation is material under the fixed power fault.

| Run | Kernel | Userspace | RasPlayer start | First pygame | Sample-list proxy | Throttle |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Original baseline | 4.147 s | 25.880 s | 29.913 s | 35.703 s | 37.001 s | `0x50005` |
| Optimization 1: mask wait, disable failover, order after sound | 4.013 s | 9.588 s | 11.449 s | 18.867 s | 20.193 s | `0x50005` |
| Iteration 2: additionally early-load `snd_bcm2835` | 4.012 s | 9.497 s | 11.756 s | 18.698 s | 20.009 s | `0x50005` |

Iteration 2 did not improve the actual ALSA gate: `sound.target` was reached at
11.418 s in optimization 1 and 11.689 s in iteration 2. The 0.184 s proxy
difference came from normal variation in subsequent Python startup. The extra
module-load file is therefore removed. The selected configuration's safe
Linux-relative local-readiness result is approximately 20 s; physical
power-on-to-ready was observed around 27 s. This is a large improvement, but
not a 3–5 s result.

## Exact current ordering path

The live unit has `Wants=sound.target` and:

```text
rasplayer.service
  -> sound.target
     -> alsa-restore.service
        -> basic.target
           -> sockets.target -> sysinit.target
              -> systemd-tmpfiles-setup -> local-fs.target -> boot/fsck
```

On the optimized boot, `sound.target` was active at 7.404 s in systemd's
userspace clock (11.418 s kernel-monotonic), and RasPlayer started at 11.449 s.
`multi-user.target` was reached later at 9.332 s userspace, proving it is no
longer on the RasPlayer critical path. `NetworkManager-wait-online` was masked;
Wi-Fi still reached DHCP at 23.708 s and SSH listened at 13.340 s.

The onboard PCM device is initialized by the kernel/udev before the sound
target; `alsa-restore.service` is the effective userspace audio ordering gate.
The device unit itself is not active in this systemd release, so requiring a
`dev-snd-*.device` unit would risk an indefinite wait and was not used.

## Startup profile (no behavior change)

A temporary wrapper executed the unchanged `RasPlayer.py` under the real
working directory and logged import/function timings; it was removed from the
Pi and repository afterward. A separate `-X importtime` run confirmed the same
breakdown.

Warm, page-cached wrapper timings (wall time from process start):

| Work | Measured time / evidence | Interpretation |
| --- | ---: | --- |
| Python/site/interpreter before project imports | included in ~0.3 s to VLC import | Not the dominant cost. |
| `vlc` import | ~0.29 s | Binding import only; `vlc.Instance`/player creation follows imports and is modest. |
| `MusicPlayer` import | ~0.25 s | Pulls in asyncio/threading/queue through its module imports. |
| `pygame` import tree | ~2.0 s | Largest group; includes SDL/SDL_mixer, `pygame.surfarray`, numpy (~0.95 s), and package-resource parsing (~0.85 s). |
| `fluidsynth` + `SynthPlayer` import | ~0.18 s | Binding import, not synth server startup. |
| GPIO setup | ~0.5 ms for all calls | Not a startup bottleneck. |
| `amixer` in `setVolume(80)` | ~55 ms (one invocation; wrapper was applied repeatedly in the diagnostic and printed duplicate samples) | Small fixed subprocess cost. |
| `glob` system-sample discovery | ~4 ms, three files | Negligible. |
| `pygame.mixer.Sound` for three startup MP3s | ~53 ms total | Not a bottleneck. |
| Explicit sleeps | none in system-sound startup path | The 0.35/0.2/0.325/0.2 s sleeps belong to non-system sample-mode construction later. |

The warm wrapper reached the first pygame line at about 2.03 s and completed
the system-sample setup shortly afterward. Cold boot journal deltas were much
larger: 6.94–7.17 s from service spawn to the first pygame line and roughly
8.25–8.51 s to the sample-list proxy. This gap is consistent with SD page
faults, cold dynamic-library loading, and CPU contention/throttling during
boot; it is not evidence of a hidden seven-second sleep.

No network operation occurs in the startup path. The first local audio response
requires GPIO setup, ALSA/pygame mixer initialization, volume setting, discovery
and loading of the three system MP3s, and callback registration. It does not
require VLC playback, FluidSynth server startup, numpy calculations, or Wi-Fi.
However, the current module-level imports load all of those bindings before
that boundary.

## Deferred-initialization candidates

For a later application task (not implemented here):

- move `MusicPlayer`, `OnlinePlayer`, `SynthPlayer`, `numpy`, and FluidSynth
  imports behind mode selection or worker initialization;
- consider a minimal local-audio entry path that imports only GPIO, pygame,
  and the system-sample loader;
- defer `vlc.Instance`/media-player creation until Music or Online mode;
- initialize FluidSynth and load the soundfont only when Synth mode is selected;
- keep Wi-Fi/radio setup outside the local-ready path and add bounded radio
  failure recovery later;
- avoid moving the existing user-visible startup sound or GPIO semantics until
  hardware measurements prove equivalence.

The profile does not prove that every deferred import is safe independently:
module globals, callback registration, and shared ALSA ownership must be
refactored and tested in a future behavior-changing task.

## Lazy-startup implementation benchmark

The application was then changed to keep only the pygame/system-sample path in
the startup import graph. `vlc`, `MusicPlayer`, `OnlinePlayer`, FluidSynth,
numpy, and MusicPlayer's asyncio/threading imports now occur on first mode use.
Monotonic markers were added for Python entry, minimum imports, GPIO, audio,
system sounds, callback registration, `LOCAL_READY`, and mode initialization.
No optional component is initialized before `LOCAL_READY`.

Three controlled cold boots with the fixed `0x50005` throttle state produced:

| Boot | Kernel + userspace | Python entry | `LOCAL_READY` | Kernel-relative ready | Service-start → ready |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 4.005 + 9.764 s | 12.776 s | 18.791 s | 18.791 s | 7.219 s |
| 2 | 4.005 + 9.750 s | 12.694 s | 18.776 s | 18.776 s | about 7.3 s |
| 3 | 4.010 + 9.507 s | 12.525 s | 18.683 s | 18.683 s | about 7.3 s |

The previous unchanged application was about 20.0 s kernel-relative and about
8.5 s from the service-start log to its readiness proxy. The refactor therefore
saves approximately 1.3–1.5 s on cold boots. Warm restarts reached
`LOCAL_READY` in 2.68–2.74 s from Python entry.

The service remains active with `NRestarts=0`. A temporary smoke harness also
initialized all three deferred modes successfully: MUSIC took about 2.5 s on
first use (including VLC creation), ONLINE about 1.5 s, and SYNTH about 8.1 s
including FluidSynth/soundfont startup. These first-use delays occur after local
controls are already active. The harness and all temporary Pi files were
removed afterward.

The physical power-on-to-ready value was not re-measured with an external
instrument on these runs; using the established ~6–7 s pre-kernel inference,
the new kernel-relative result corresponds to roughly 25 s physical startup.
This remains approximate while under-voltage is active.

## Remaining boot path and Buildroot implication

Kernel initialization remains about 4.0 s. The Pi's firmware/bootloader runs
before Linux monotonic timestamp zero and does not expose a reliable duration
through the current userspace. Subtracting the measured ~20.27 s Linux-relative
proxy from the ~27 s physical observation suggests roughly 6–7 s before the
kernel timeline, but that includes power-on observation and is an inference,
not a firmware measurement. No firmware change was attempted.

With the lazy startup path, Raspberry Pi OS is around 18.7–18.8 s from the
kernel timeline (approximately 25 s using the prior physical pre-kernel
inference). Further safe service disabling is unlikely to remove the ALSA gate.
The remaining cold cost is primarily pygame's native/numpy import tree. Even
after this application improvement, the OS's inferred 6–7 s pre-kernel
interval and ~4 s kernel make 3–5 s power-on-to-ready unrealistic without
aggressive kernel/firmware/init changes. Buildroot remains justified for
deterministic minimal userspace and boot-path reduction, but it will not by
itself remove Python's cold import cost.

## Final focused bottleneck investigation (2026-08-28)

**Verified on the Pi:** A fresh boot measured 4.210 s kernel and 9.823 s userspace. `sound.target` became active at 7.314 s in the userspace clock (11.524 s kernel-relative); `alsa-restore.service` completed at 6.954 s userspace and took 322 ms. `/dev/snd/pcmC0D0p` and `snd_bcm2835` were already present before the sound target gate. The critical chain is filesystem fsck/mount → tmpfiles → timesyncd → sockets → `alsa-restore` → `sound.target`; replacing the gate with a device unit is unsafe because this system does not expose a stable `dev-snd-*.device` ordering unit. There is no evidence for a removable multi-second ALSA restore delay.

The current cold pygame/SDL path remains the dominant application cost (about 5.4–5.5 s to minimum imports). The Pi has `/usr/bin/mpg123`; a direct MP3 playback test succeeded (`rc=0`) and a background launch remained alive after 0.208 s. This demonstrates a plausible startup-sound-only alternative, but does not prove first-audio latency, mixer coexistence, or reliable behavior under the appliance amplifier. It was not substituted in production; an A/B prototype with an external audible/line-level measurement is required before claiming the potential ~5 s saving.

Firmware/configuration inspection found standard `dtparam=audio=on`, `dtoverlay=vc4-kms-v3d`, camera/display auto-detection, and no configured boot delays. `vcgencmd` exposes firmware version but no trustworthy firmware-duration timestamp. The inferred 6–7 s pre-kernel interval therefore remains unmeasured; no firmware change was applied. Disabling auto-detection or changing bootloader settings is not justified without evidence of a multi-second gain and carries headless/audio regression risk.

## mpg123 startup-sound optimization (2026-08-28)

**Verified:** `RasPlayer.py` no longer imports `SamplePlayer`/pygame before readiness. It launches `mpg123 -q -o alsa ./Sounds/System/0/TurnOn.mp3`, confirms the process has not failed after 100 ms, and only then emits `audio_ready`, `system_sounds_ready`, and `LOCAL_READY`. The existing pygame `SamplePlayer` remains available through `ensure_sample_player()` for volume sounds and sample modes; any still-running mpg123 child is stopped before pygame initializes and is reaped by the owner tick.

If mpg123 cannot launch or exits unsuccessfully, startup falls back to pygame, plays the same `TurnOn.mp3`, and only then emits `LOCAL_READY`; therefore readiness still implies a usable startup-sound path, at the cost of the old cold-start time on that exceptional path.

Three controlled reboots on `dnl@192.168.0.70` (all `0x50005`) produced:

| Boot | Kernel + userspace | Service start | Python entry | mpg123 trigger | `LOCAL_READY` | Kernel-relative ready |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4.018 + 9.663 s | 11.483 s | 12.786 s | 13.241 s | 13.305 s | 13.305 s |
| 2 | 4.014 + 9.870 s | 11.535 s | 12.809 s | 13.251 s | 13.406 s | 13.406 s |
| 3 | 4.012 + 9.775 s | 12.059 s | 13.119 s | 13.463 s | 13.553 s | 13.553 s |

Python-entry-to-ready was 0.434–0.598 s, versus 5.8–6.0 s with pygame in the critical path. Kernel-relative readiness improved from approximately 18.7 s to 13.3–13.6 s, a repeatable saving of roughly 5.2–5.4 s. The physical power-on → audible startup sound still requires the owner's external measurement. The first-audio check is process/device based rather than an electrical measurement, so amplifier audibility should be confirmed physically.

## First Buildroot physical result and timeline image (2026-08-29)

**Verified on the physical Pi 3B+:** the first Buildroot image boots and reaches
an audible startup sound in approximately 16 seconds from power application,
versus approximately 19–20 seconds for the optimized Raspberry Pi OS image.

No further optimization was selected from that aggregate number. The next
image adds BusyBox-compatible kernel-uptime instrumentation around the full
init sequence, ALSA-node availability, RasPlayer launch, Python entry, mpg123,
and `LOCAL_READY`. It saves the combined event/kernel report to the FAT boot
partition after readiness for retrieval without Wi-Fi. The exact procedure and
current non-conclusive delay candidates are documented in
`docs/buildroot-boot-instrumentation.md`.
