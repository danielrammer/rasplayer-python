# Stability and event model

## Implemented command ownership

**Verified from current source:** GPIO callbacks and VLC end callbacks are
lightweight producers. They timestamp and submit commands to a bounded queue
(`64` entries). A natural Music end event submits `automatic_next`, distinct
from physical navigation. One daemon `SerializedCommandPath` thread is the
sole owner of active `soundPlayer`, `playerMode`, mode-generation acceptance,
playback commands, and periodic `update()`. Each dequeue logs enqueue/dequeue
time, queue wait, depth, handler duration, result, exceptions, and slow ticks.

The mode lifecycle remains `NONE`, `INITIALIZING`, `ACTIVE`, `STOPPING`, or `FAILED`, but potentially blocking backend stop and construction now run on daemon workers. The owner increments a generation, detaches the prior active object, and later accepts a `_mode_ready` result only if its generation is still current. Stale completions are torn down off-thread. Commands continue to dequeue while a mode is preparing; transport/generic commands have no target until that generation becomes active.

Short UI feedback is also delegated: accepted actions enqueue an allowlisted
sound request to one bounded worker, which serializes mpg123 processes and
records queue time, duration, exit status, and stderr. Failed, stale, ignored,
or unsupported actions do not enqueue feedback. Mode acknowledgement is
submitted immediately after transition acceptance, before cleanup/init, and
is not repeated at `MODE active`. This keeps MP3 playback and
its bounded three-second failure path outside the serialized owner.

The allowlist maps mode changes to `mode-switch.mp3`, volume direction and
maximum to `vol-up.mp3`, `vol-down.mp3`, and `vol-max.mp3`, and accepted
physical navigation/selection/transport actions to `generic.mp3`. Natural
playback progression is not a user acknowledgement and is always silent.

## Resource lifecycle

**Verified from current source:** The libVLC instance remains process-owned, but each mode gets a dedicated media player. This prevents a slow network-player stop from blocking or corrupting the player used by local MP3. `MusicPlayer.stop()` detaches its end callback; Synth stop/delete is timed off-thread. Before Synth starts, pygame is invalidated and its mixer is closed so the exclusive Buildroot ALSA `hw:0,0` path is available. Transitions to/from Synth wait, off-thread and for at most five seconds, for prior cleanup.

## Remaining physical risks

Online state polling remains an owner-thread tick. Online logs every VLC state
transition and an eight-second open failure/timeout without synchronously
stopping the player. Synth ultrasonic polling now runs on a mode-owned worker
with 30 ms edge bounds and a 100 ms inter-measurement pause; the owner reads the
latest sample without waiting. Worker shutdown is bounded and participates in
the existing off-thread Synth cleanup. Physical hand/pitch response and
repeated post-change Synth transitions still require Pi validation.

**Pi-verified 2026-08-31:** A generic Synth event now calls FluidSynth
`program_select()` and `noteon()` directly on the serialized owner. Both
returned `0` on the physical Pi. The prior successful `generic` command did
not imply a note: during initialization it silently had no active player, and
after initialization `buttonDown()` changed only the program while a later
tick could suppress the note for an invalid sensor sample. Both skip/call
paths are now explicit in diagnostics.

## Test and deployment status

`tests/test_command_path.py` covers FIFO ordering, handler-failure recovery, bounded queues, the prior synchronous-delay model, delegated slow work, and a burst of 20 alternating mode/input commands. The host stress run on 2026-08-29 measured 200.131 ms queue wait behind a simulated 200 ms synchronous initializer versus 0.151 ms for one delegated transition and 2.560 ms maximum across the 40-command burst. These are architecture tests, not Pi latency measurements.

## Rapid-input coalescing (2026-08-31)

**Verified from source:** Coalescing is opt-in by command category. Commands
without a policy remain FIFO and bounded by the existing 64-entry limit.
Coalesced entries move to the newest input's position, so unrelated pending
commands retain chronological order.

- `volume_delta` sums pending 10-percent changes. Opposing changes cancel a
  pending entry at zero, and the owner makes one clamped `amixer` call for the
  resulting target.
- `navigation_delta` sums next/previous offsets. Music and sample players
  calculate the final wrapped item and open/load it once. Online calculates
  the final wrapped page without opening a station; its five station buttons
  retain latest-value selection coalescing.
- Music playlist and Online station selectors use latest-value replacement,
  tagged with mode and generation. A selection from an obsolete mode
  generation is skipped.
- Mode requests use latest-value replacement. The existing generation check
  remains authoritative; a producer-side cancellation event also prevents
  superseded workers from beginning later backend stages where possible.
  Constructors already inside an uninterruptible library call finish and are
  cleaned as stale off-thread.
- Generic Synth/sample commands, play/pause, `_mode_ready`, lifecycle work,
  natural `automatic_next`, and all other command types remain FIFO and are
  never coalesced. Synth down/up therefore cannot be dropped or reordered.
- The separate feedback worker keeps at most one pending acknowledgement for
  each coalescible category. Feedback for unrelated actions remains ordered.

Every enqueue now logs queue depth. Dequeue logs oldest and latest enqueue
times, queue wait, depth, and represented input count. Completion logs handler
duration and latest-input-to-action latency. Health snapshots include totals
for coalesced, cancelled, superseded, and queue-full dropped commands.

**Pi-verified on signed release `rapid-input-20260831-1`:** The physical test
covered rapid alternating Volume Up/Down, repeated Volume Up, Music playlist
and track navigation, Online station navigation, rapid Music/Online/
Instrument/Synth changes, Synth generic input, and normal presses afterward.
Across 133 completed commands, maximum queue depth was 4, maximum queue wait
was 110.156 ms, maximum input-to-action completion was 226.378 ms, and there
were no command drops or handler exceptions. Category maxima were 221.785 ms
for volume (during concurrent backend initialization), 226.378 ms for
selection, 4.603 ms for navigation, 15.271 ms for accepted mode work, and
19.744 ms for uncoalesced generic input.

One pending mode request was coalesced, two obsolete mode workers were
cancelled before backend construction, and three workers already inside
backend initialization completed and were cleaned as stale. Feedback
superseded 29 pending acknowledgements. The worst observed feedback wait fell
from the pre-change physical-log baseline of 7,511.814 ms to 812.920 ms; the
remaining case was the then-current maximum-volume acknowledgement, not a
multi-action backlog. A later feedback-sound update replaced that historical
cue with the dedicated `vol-max.mp3`. Online radio DNS/connection errors
occurred during the test, but command ownership remained responsive and the
final requested selection was retained.

## Silent automatic Music progression (2026-08-31)

**Pi-verified on signed release `track-end-feedback-20260831-1`:** The VLC
natural-end callback now submits `automatic_next` instead of reusing the
physical `next` input. Two observed automatic advances completed with 4.559 ms
and 7.297 ms input-to-action latency and emitted no feedback request. Physical
Next, playlist selection, and Play/Pause retained their intended audible
acknowledgements. The regression test asserts the callback's distinct command
identity so natural playback cannot silently re-enter the user-feedback path.

**Regression restored on 2026-09-01:** the freshly flashed Buildroot
`image-base` contained the pre-fix `MusicPlayer.py` and `RasPlayer.py`. Its live
log showed `Song ended` enqueueing `navigation_delta`, followed by
`FEEDBACK ... source=navigation`. Signed release
`music-radio15-20260901-1` restored the current source through the normal SSH
installer while retaining `image-base` as the rollback target. On the Pi, a
subsequent natural end enqueued distinct `automatic_next`, advanced in 7.503 ms,
and emitted no feedback request. Owner-path regression coverage now also
asserts exactly one generic acknowledgement for accepted physical Prev/Next,
playlist selection, and Music Play/Pause actions.

Final follow-up release `music-radio15-20260901-2` retains those Music files
unchanged while completing Online-radio compatibility. It is the active
release; `music-radio15-20260901-1` is the atomic rollback target and
`image-base` remains installed as the original image release.

## Deployment validation (2026-08-28)

**Verified on Pi:** The six runtime modules plus `command_path.py` were copied to `/home/dnl/RasPlayer`. The service restarted successfully, stayed active, and retained `NRestarts=0`. NetworkManager and SSH remained active. The journal showed all startup markers and no startup exception; no `vlc_init` or mode initialization occurred before `LOCAL_READY`.

Three controlled reboots produced:

| Boot | kernel | userspace | service start (kernel-relative) | Python → LOCAL_READY | LOCAL_READY (kernel-relative) | throttling |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 4.016 s | 9.758 s | 11.667 s | 5.875 s | 18.833 s | `0x50005` |
| 2 | 4.009 s | 9.496 s | 11.608 s | 5.906 s | 18.698 s | `0x50005` |
| 3 | 4.010 s | 9.828 s | 11.434 s | 6.036 s | 18.720 s | `0x50005` |

The Python-entry-to-ready interval was 5.875–6.036 s; service-start-to-ready was 7.09–7.29 s, improving on the prior ~8.5 s application interval. Physical power-on → startup sound remains the independently measured ~25 s baseline; it was not remeasured remotely. Remote checks confirmed five process threads (including SDL threads), no restart or journal error, and a live command-owner worker inferred from the deployed runtime thread set. Physical button/audio and repeated mode-transition tests remain outstanding.

Rollback copy currently retained on the Pi: `/home/dnl/RasPlayer-backup-stability-20260828-2212`. It contains the deployed stability version and is useful for recovery from accidental file damage. The earlier pre-deployment copy was mistakenly placed under `/tmp` and disappeared during reboot; a pre-stability known-good copy must be recreated from a separate backup before any further risky deployment. To restore the retained copy: stop the service, copy its files back to `/home/dnl/RasPlayer`, then start the service.

The deployed queue was exercised remotely with commands `a`, `bad`, `c`; it preserved FIFO order, logged the injected exception, and continued processing (`['a', 'bad', 'c']`). This does not substitute for hardware/button or backend transition testing.

## Watchdog supervision (2026-08-28)

**Verified:** `systemd_notify.py` sends `READY=1` after `LOCAL_READY` and sends `WATCHDOG=1` from the serialized command-owner tick. The service uses `WatchdogSec=20s`, `NotifyAccess=all`, `Restart=always`, `RestartSec=2s`, and a `StartLimitBurst=5`/`StartLimitIntervalSec=60` guard. Health therefore means that the owner loop is executing its 50 ms tick and the process can notify systemd; a process blocked in mode initialization or a stopped process stops heartbeats and is restarted.

Crash test: `SIGKILL` of the main process produced a systemd restart (`NRestarts=1`) and a new `LOCAL_READY`. Hang test: `SIGSTOP` of the process produced `Watchdog timeout (limit 20s)`, systemd killed/restarted it, and `NRestarts=1` for that test sequence. No automatic reboot loop occurred. The shutdown flag prevents owner ticks from touching GPIO after signal cleanup.

Post-watchdog reboot timings were 18.769 s, 18.917 s, and 18.884 s kernel-relative to `LOCAL_READY`, with Python-entry intervals of 5.857 s, 5.842 s, and 5.792 s. This is within normal variance of the previous 18.7–18.8 s baseline; no regression over 0.5 s was observed. Every run reported throttling `0x50005`.

The BCM2835 `/dev/watchdog0` layer was not enabled. Systemd supervision detects an application hang without risking an independent hardware-reset loop; hardware watchdog support remains a later defense-in-depth step after observing watchdog behavior in longer physical operation. Rollback the watchdog change by restoring `/home/dnl/RasPlayer-backup-watchdog-pre-20260828-222258` (application files), restoring the prior unit from version control/backup, running `sudo systemctl daemon-reload`, and restarting the service.

## Watchdog recommendation

The next reliability task should add a heartbeat owned by the command thread and a conservative systemd watchdog policy. Do not enable reboot loops until heartbeat semantics and a restart-rate limit are tested. A hardware `/dev/watchdog0` can be considered after software supervision is proven.
