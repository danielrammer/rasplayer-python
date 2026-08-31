# Operations and platform

## Evidence convention

This document describes the current Buildroot deployment as reviewed on
2026-08-31. **Verified** is supported by tracked material or an explicitly
identified physical-Pi test. **Inference** is a risk assessment. **Open
question** requires device or wiring evidence.

The earlier Raspberry Pi OS/systemd measurements remain in
`docs/existing-pi-baseline.md` and the first sections of
`docs/pi-boot-optimization.md`; they are historical rather than current
deployment instructions.

## Current production platform

**Verified:** Production targets a Raspberry Pi 3B+ with the external
Buildroot tree in `buildroot/`, pinned to Buildroot 2024.02.9. BusyBox `rcS`
starts provisioning, Wi-Fi, Dropbear, and RasPlayer. Networking and SSH are
asynchronous and do not gate local readiness. ALSA defaults to card 0 and the
application controls its `PCM` mixer through `amixer`.

`S50rasplayer` supervises the application manager and child with bounded
restart behavior and an owner-thread heartbeat. Persistent bounded logs live
under `/var/lib/rasplayer/logs`; boot and diagnostic snapshots are also copied
to the FAT boot partition. `LOCAL_READY` means the GPIO callbacks are installed
and the startup cue was launched successfully.

The current physical power-on-to-audible observation remains about 10 seconds.
The measured kernel-relative `LOCAL_READY` boundary is about 6.2 seconds. An
early-init ordering experiment saved only 12 ms and was rejected; details and
rollback image identity are in `docs/pi-boot-optimization.md`.

## Runtime requirements

The image and deployment must preserve:

- Pi 3B+ firmware/kernel, BCM GPIO numbering, `/dev/gpiomem`, and the pin
  assignments in `GPIO-Mapping.md`;
- Python 3, RPi.GPIO, libVLC/python-vlc, pygame/SDL_mixer, FluidSynth with its
  Python binding, ALSA utilities, and mpg123;
- `/usr/share/sounds/sf2/FluidR3_GM.sf2`;
- an ALSA card/control compatible with card 0 and `PCM`;
- the application working directory and shared media layout under
  `/home/dnl/RasPlayer`;
- Wi-Fi firmware, wpa_supplicant, DHCP, DNS, and VLC HTTP support for Online
  radio;
- key-only Dropbear access, the signed-update public key, atomic release
  installer, rollback, service-control helper, and recovery logs.

Three audio engines share the hardware: VLC for Music/Online, pygame for
samples, and FluidSynth for Synth. mpg123 is a fourth short-lived client for
startup and feedback. Mode teardown/construction is serialized through
generation-checked workers, and pygame is released before Synth takes the
exclusive Buildroot ALSA path.

## Deployment and recovery

**Verified:** Application releases are immutable and root-owned below
`/opt/rasplayer/releases`. `/opt/rasplayer/current` switches atomically and
`/opt/rasplayer/previous` is the rollback target. SSH user `dnl` may upload only
to `/home/dnl/work`; arbitrary root-owned Python cannot be activated without a
valid Ed25519 manifest signature.

Normal application changes use:

1. `buildroot/scripts/build-rasplayer-update.sh` with a unique release ID and
   the matching `rasplayer-service` binary;
2. `buildroot/scripts/deploy-rasplayer-update.sh` with the dedicated
   `~/.ssh/rasplayer_buildroot_ed25519` identity;
3. `rasplayer-service status` plus physical functional checks.

The installer verifies the fixed allowlist and hashes, fsyncs a new release,
switches atomically, waits for manager/child/`LOCAL_READY`, and automatically
rolls back a failed health check. `rasplayer-service rollback` provides manual
recovery. Full instructions and the trust boundary are in
`docs/buildroot-ssh-development.md`.

A Buildroot rebuild and SD-card flash are still required for kernel, firmware,
device tree, packages/libraries, BusyBox/init, users/permissions, filesystem or
partition changes, provisioning, Dropbear, the verifier itself, or public-key
trust changes. Preserve the known-good image and the three uncommitted FAT
provisioning inputs (`wifi.network`, `dnl_authorized_keys`, and
`rasplayer-update-public.pem`) before flashing.

## Current event and safety model

**Verified:** GPIO/VLC callbacks enqueue timestamped work into a bounded
64-entry queue. One owner thread applies playback state. Volume, navigation,
selection, and pending mode requests have explicit coalescing policies;
unrelated commands remain ordered. Synth press/release and `_mode_ready` are
strict FIFO. Natural Music progression uses a separate silent
`automatic_next` command and cannot enqueue physical-action feedback.

Mode generation checks prevent an obsolete initializer from becoming current.
Stale backends are cleaned away from the owner thread. The Synth ultrasonic
worker publishes only its latest measurement, and cleanup cannot target the
accepted live instance through a stale completion. See
`docs/stability-and-event-model.md` for measured latency and regression
validation.

## Remaining operational risks

| Risk | Current mitigation | Validation |
| --- | --- | --- |
| Shared ALSA hardware | Separate mode players, off-thread cleanup, pygame release before Synth | Repeat Synth ↔ Music/Sampler and inspect audio/process logs after audio changes |
| Missing/empty media | Deployment checks system cues; players log/guard several empty selections | Validate the complete external media tree before release |
| Online endpoint/DNS failure | Network does not gate local ready; Online reports state and an 8 s open timeout | Test disconnected Wi-Fi and dead station URLs |
| Ultrasonic wiring/noise | Dedicated worker with bounded edge timeouts and rate-limited invalid samples | Run `rasplayer-service ultrasonic-test` with player stopped |
| SD/power failure | Atomic releases, rollback symlink, persistent bounded diagnostics | Use a healthy supply/card and preserve a known-good image |
| Firmware/kernel boot delay | Timestamped boot trace and conservative known-good configuration | Require measured gains and rollback before risky pruning |

**Open question:** The repository does not identify the exact ultrasonic
module, echo voltage-level conversion, audio adapter/DAC/amplifier, or button
circuit. Physical wiring must be checked before changing pull modes, voltage
assumptions, or pin assignments.

## Routine diagnostics

```sh
rasplayer-service status
rasplayer-service restart

rasplayer-service stop
rasplayer-service ultrasonic-test
rasplayer-service start
```

Primary logs:

- `/var/lib/rasplayer/logs/rasplayer.log`;
- `/var/lib/rasplayer/logs/rasplayer-supervisor.log`;
- `/var/lib/rasplayer/logs/rasplayer-network.log`;
- `/var/lib/rasplayer/logs/rasplayer-diagnostics.txt`;
- `/var/log/boot-timeline.txt` and its FAT-partition copy.

Host unit tests are useful but do not replace physical GPIO/audio validation.
Run the full suite from the repository root with
`python3 -m unittest discover -s tests -v`.
