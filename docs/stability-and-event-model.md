# Stability and event model

## Implemented command ownership

**Verified:** GPIO callbacks and VLC end callbacks are now lightweight producers. They submit `(command, value)` tuples to a bounded queue (`64` entries). One daemon `SerializedCommandPath` thread is the sole owner of `soundPlayer`, `playerMode`, mode construction, playback commands, and the periodic `update()` call. Handler exceptions are logged and do not terminate the worker; a full queue drops the newest command and logs it.

The mode lifecycle is represented by `mode_state`: `NONE`, `INITIALIZING`, `ACTIVE`, `STOPPING`, or `FAILED`. A transition stops the previous backend, performs initialization atomically on the owner thread, and leaves `NONE`/`FAILED` if initialization fails. Buttons received while initialization is running remain queued and execute in order afterward; callbacks themselves do not block on initialization.

## Resource lifecycle

**Verified:** The shared VLC player remains process-owned and is reused across modes. `MusicPlayer.stop()` detaches its `MediaPlayerEndReached` callback before stopping, preventing stale instances from receiving end events. Synth shutdown attempts `stop()` and always `delete()`s the FluidSynth object, including repeated mode switches. pygame's mixer remains process-owned because system sounds depend on it and is not torn down during mode changes.

## Risks intentionally left for the stability follow-up

First-use mode initialization is still synchronous on the owner thread (Music/Online/Synth can take seconds), so playback commands queue during that interval. Network/VLC operations may still block the owner thread. GPIO bounce settings remain the primary burst limiter. Physical button/audio regression testing is still required on the appliance.

## Test and deployment status

`tests/test_command_path.py` covers FIFO ordering, handler-failure recovery, and bounded queue behavior with no GPIO/audio hardware. A Pi deployment and controlled smoke test must verify all modes and repeated transitions; record `vcgencmd get_throttled` with timing because the device reports `0x50005`.

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
