# RasPlayer

RasPlayer is a physical music and sound player for a Raspberry Pi 3B+. GPIO
buttons and mode cables control local Music, an Instrument sampler, Online
radio, and a distance-controlled FluidSynth synthesizer.

`RasPlayer.py` is the production entry point. The application intentionally
remains a flat Python program. Production runs on a pinned Buildroot image
with BusyBox init; the older Raspberry Pi OS/systemd installation is retained
only as historical documentation.

## Runtime architecture

One bounded, serialized command path owns player state. GPIO and VLC callbacks
capture and enqueue events instead of operating audio backends. Slow mode
construction and teardown use generation-checked workers, while UI sounds use
a separate bounded `mpg123` feedback worker.

The audio paths are deliberately separate:

- libVLC plays local Music and Online radio;
- pygame/SDL_mixer plays Instrument samples;
- FluidSynth plays Synth notes, with pitch controlled by the ultrasonic sensor;
- `mpg123` plays startup and UI acknowledgement sounds.

Coalescing is opt-in. Pending volume deltas and navigation offsets are summed,
playlist/station selection keeps the latest value, and pending mode requests
are latest-wins. Synth press/release events, `_mode_ready` lifecycle results,
natural track progression, and commands without an explicit policy remain
strict FIFO. This preserves state and lifecycle safety without replaying stale
UI input.

See [docs/architecture.md](docs/architecture.md) and
[docs/stability-and-event-model.md](docs/stability-and-event-model.md) for the
full control flow, instrumentation, and physical validation.

## Controls and input semantics

GPIO uses BCM numbering. [GPIO-Mapping.md](GPIO-Mapping.md) is the wiring
authority.

| Control | BCM | Behavior |
| --- | ---: | --- |
| Play/Pause | 4 | One action on press |
| Next / Previous | 17 / 27 | One action on press; rapid offsets coalesce |
| Volume up / down | 22 / 23 | One action on press; rapid deltas coalesce |
| Music / Online / Synth mode | 24 / 10 / 9 | Rising mode-cable request; latest pending mode wins |
| Instrument sampler mode | 25 | Rising mode-cable request; latest pending mode wins |
| Generic buttons | 11, 5, 6, 19, 16 | Meaning depends on the active mode |
| Ultrasonic trigger / echo | 14 / 15 | Synth pitch measurement |
| Status LED | 26 | Output |

Generic edge levels are explicit command data. Music playlist, Online station,
and Instrument sample actions are press-only; release is ignored. Synth is
stateful and strict FIFO: press starts and holds a note, while release stops
it. Input received without an active player is ignored and logged, not replayed
later. The Animals mode remains in source but has no enabled selector.

## Feedback sounds

System sounds live in `Sounds/System/0`. Feedback is asynchronous and is
queued only after an action is accepted and applied.

| Event | Sound |
| --- | --- |
| Application startup | `TurnOn.mp3` |
| Accepted mode request | `mode-switch.mp3` |
| Applied volume increase / decrease | `vol-up.mp3` / `vol-down.mp3` |
| Volume-up while already at maximum | `vol-max.mp3` |
| Physical Prev/Next, Music/Online selection, Music/Online Play/Pause | `generic.mp3` |

There is no UI feedback for press-only releases, ignored/failed actions, stale
mode work, Sampler/Synth sound production, natural Music track end, or its
automatic next-track action. Coalescible feedback retains only the latest
pending acknowledgement, preventing a stale audible tail.

Most of `Sounds/` is intentionally ignored by Git and separately managed. Do
not assume a checkout contains production media. The deployment helper checks
and uploads the six current system sounds alongside a signed update.

## Buildroot platform and startup

The external tree under `buildroot/` pins Buildroot 2024.02.9. The image uses
BusyBox init, asynchronous Wi-Fi and Dropbear, key-only SSH, bounded persistent
logs, application heartbeat supervision, and atomic releases:

- `/opt/rasplayer/releases/<release>` — immutable releases;
- `/opt/rasplayer/current` — active release symlink;
- `/opt/rasplayer/previous` — rollback target;
- `/home/dnl/RasPlayer/Sounds` — shared media;
- `/home/dnl/work` — unprivileged upload staging.

`S50rasplayer` starts the manager/watchdog. Python defers VLC, pygame,
FluidSynth, numpy, and mode imports. `LOCAL_READY` means controls are registered
and startup audio was launched. The measured boundary is about 6.2 seconds
from kernel start and about 10 seconds from physical power-on. An experiment
starting RasPlayer earlier in `rcS` improved `LOCAL_READY` by only 12 ms and
was rejected; see [docs/pi-boot-optimization.md](docs/pi-boot-optimization.md).

Build and first-boot provisioning are covered by
[buildroot/README.md](buildroot/README.md) and
[docs/buildroot-remote-development.md](docs/buildroot-remote-development.md).
Kernel, firmware, packages, init, filesystem, or trust-base changes require an
image rebuild/flash. Allowed application updates do not.

## Development and tests

Run from the repository root so relative `./Sounds/...` paths match the Pi.
The host suite mocks hardware where required:

```sh
python3 -m unittest discover -s tests -v
```

`tests/underrun_test.py` is a separate manual Pi audio diagnostic. Runtime
changes also require physical checks because host tests cannot prove GPIO and
shared ALSA behavior. Read `AGENTS.md` before runtime changes.

## Signed SSH deployment

Normal development uses a dedicated SSH identity and a separate offline
Ed25519 release-signing key. Never copy or commit the root-equivalent private
signing key; the Pi stores only its provisioned public key.

Create or verify the pair once:

```sh
sh buildroot/scripts/create-update-signing-key.sh
```

Build a complete bundle with a new release ID and the helper binary from the
matching Buildroot output:

```sh
sh buildroot/scripts/build-rasplayer-update.sh \
  dev-YYYYMMDD-1 \
  /home/dnl/rasplayer-build/output/target/usr/bin/rasplayer-service \
  /tmp/rasplayer-update-dev-YYYYMMDD-1
```

Deploy through SSH:

```sh
sh buildroot/scripts/deploy-rasplayer-update.sh \
  dnl@192.168.0.70 \
  /tmp/rasplayer-update-dev-YYYYMMDD-1 \
  ~/.ssh/rasplayer_buildroot_ed25519
```

The installer verifies the signature and fixed payload, creates a root-owned
release, atomically switches `current`, restarts the player, checks
manager/child/`LOCAL_READY` health, and automatically restores the previous
release on failure. Release IDs cannot be reused.

Useful operations:

```sh
rasplayer-service status
rasplayer-service restart
rasplayer-service rollback

rasplayer-service stop
rasplayer-service ultrasonic-test
rasplayer-service start
```

Persistent logs are `/var/lib/rasplayer/logs/rasplayer.log` and
`/var/lib/rasplayer/logs/rasplayer-supervisor.log`. See
[docs/buildroot-ssh-development.md](docs/buildroot-ssh-development.md) for the
security boundary, rollback, and image-only changes.

## Documentation map

- [docs/architecture.md](docs/architecture.md) — structure, controls, modes,
  and audio ownership.
- [docs/stability-and-event-model.md](docs/stability-and-event-model.md) —
  serialization, coalescing, lifecycle, watchdog, and validation.
- [docs/operations-and-platform.md](docs/operations-and-platform.md) — current
  platform assumptions and remaining hardware risks.
- [docs/existing-pi-baseline.md](docs/existing-pi-baseline.md) — historical
  Raspberry Pi OS measurements.
- [docs/pi-boot-optimization.md](docs/pi-boot-optimization.md) and
  [docs/buildroot-boot-instrumentation.md](docs/buildroot-boot-instrumentation.md)
  — boot measurements and instrumentation.
- [docs/buildroot-migration-plan.md](docs/buildroot-migration-plan.md) — the
  migration planning record, now superseded where the Buildroot tree is live.
