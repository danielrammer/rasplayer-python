# rasplayer-python contributor guide

This repository runs a Raspberry Pi physical music/sound player. `RasPlayer.py` is the production entry point; it is launched as a systemd service on the Pi according to `readme.md`. It is intentionally a flat Python application, not a packaged project.

Before changing runtime behavior, read:

- `docs/architecture.md` — verified architecture, inputs, modes, audio stack, and control flow.
- `docs/operations-and-platform.md` — deployment, Raspberry Pi assumptions, known stability risks, and Buildroot constraints.
- `docs/buildroot-migration-plan.md` — approved planning baseline for the Pi 3B+ minimal-Linux migration; do not create or write an SD image without an explicit task.
- `docs/existing-pi-baseline.md` — read-only measurements from the running Pi, including the boot timeline, exact runtime versions, and live power/network/audio findings.
- `docs/pi-boot-optimization.md` — controlled Raspberry Pi OS boot changes, rollback, before/after timing, and temporary startup profiling results.
- `docs/stability-and-event-model.md` — serialized GPIO/VLC commands, mode lifecycle, cleanup, tests, and watchdog follow-up.

Working rules:

- Preserve BCM GPIO numbering and the pin assignments in `GPIO-Mapping.md`; physical wiring depends on them.
- Treat the three audio paths (VLC, pygame, and FluidSynth) and GPIO callbacks as shared hardware resources. Test changes on the Pi; this repository has no automated application test suite.
- Relative `./Sounds/...` paths require the service working directory `/home/dnl/RasPlayer` (or an equivalent deployment layout).
- Do not assume the checked-in `Sounds/` directory is current: it is ignored for new files and separately synced by `syncSoundsToPi.sh`.
- Keep OS/service changes and dependency versions documented. They are not represented as reproducible configuration in this repository.
- Startup now has a measured `LOCAL_READY` boundary; mode-specific VLC, FluidSynth, numpy, and player imports are intentionally lazy. Preserve the markers and defer further concurrency changes to a dedicated stability task.

Facts in the detailed docs are explicitly labelled **Verified**; statements labelled **Inference** or **Open question** require validation on the actual device.
