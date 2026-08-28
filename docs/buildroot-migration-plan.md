# Buildroot migration plan for Raspberry Pi 3B+

## Decision and scope

This is a plan only. It does not change the Python application or the microSD card at `F:\`. The target remains a Raspberry Pi 3B+ and the application path remains `/home/dnl/RasPlayer`.

The existing Pi was inspected read-only on 2026-08-28. Measurements and exact runtime versions are in `docs/existing-pi-baseline.md`; those facts supersede the pre-inspection estimates in this plan.

Controlled Raspberry Pi OS optimization results and a startup profile are in
`docs/pi-boot-optimization.md`. Removing the network wait and ordering the
unchanged service after ALSA reduced local readiness to about 20 seconds from
the kernel timeline (about 27 seconds power-on observed). An early
`snd_bcm2835` module override was ineffective and was removed. Buildroot's
remaining value is deterministic minimal userspace and kernel/init pruning;
lazy application initialization is still required for a 3–5 second target.

**Recommendation:** use a pinned Buildroot release with a project-owned `br2-external` tree as the primary implementation path. Preserve current application behavior for the first bootable image, then address application reliability and boot-time optimizations as separately tested phases.

Why Buildroot:

- It can produce a small, headless image with BusyBox init, a custom kernel, and exactly the required audio/GPIO/network packages.
- Its `br2-external` mechanism is designed to keep the defconfig, board files, overlays, patches, and project-specific package recipes under version control outside Buildroot itself.
- It is appropriate for an appliance with a fixed hardware target and no runtime package manager.

Buildroot is not zero-effort because three Python layers used by this project need project packaging or vendoring. That is a manageable, explicit integration task—not a reason to alter the player during the migration.

## Alternatives considered

| Approach | Assessment |
| --- | --- |
| **Buildroot (recommended)** | Best fit for a reproducible appliance image and a short local-function boot path. Needs custom recipes/vendored Python modules for pygame, python-vlc, and pyfluidsynth. |
| Raspberry Pi OS Lite, aggressively trimmed | Lowest migration risk because Debian packages already exist, good diagnostic baseline, and easiest remote maintenance. It retains general-purpose OS startup and is unlikely to be the best route to a consistent 3–5 second appliance target. Use only as a measurement/fallback baseline. |
| Yocto/OpenEmbedded | Technically capable and has stronger long-term package/layer tooling, but is substantially heavier to develop and maintain. It offers no intrinsic boot-time advantage over an equivalently configured Buildroot image for this one-device appliance. |
| piCore/Tiny Core or a hand-built distro | Can boot quickly, but would shift reproducibility, cross-build, dependency integration, and update responsibility onto this project. Not recommended with VLC, pygame, and FluidSynth still required. |

## Dependency feasibility

The Buildroot observations below were checked against the current upstream package tree on 2026-08-28. A real build must pin a tested Buildroot release and revalidate its exact symbols and versions; do not build from `master`.

| Existing dependency / requirement | Buildroot path | Initial migration action | Main impact or caveat |
| --- | --- | --- | --- |
| Python | Upstream `python3` | Enable dynamic Python 3 with `.pyc`-only target modules unless source files are needed for field debugging. | Moderate image/runtime cost; required by current app. |
| libVLC | Upstream `vlc` with ALSA and MP3 support | Enable only headless/audio and required HTTP/MP3 codecs; omit GUI/video, DBus, PulseAudio, X11, and unneeded protocols. | Largest dependency graph and a long cross-build; notable rootfs size. |
| `python-vlc` | No upstream recipe found in the current package tree | Add a project recipe or vendor the pinned `vlc.py` binding as part of the application image. Validate ABI/API against the pinned libVLC. | Small Python layer, but libVLC remains the real complexity. |
| pygame / SDL mixer | No upstream pygame recipe found in the current package tree; SDL2/SDL2_mixer are upstream packages | Add a pinned project recipe for pygame, configured against SDL2 and SDL2_mixer with MP3 decoding. | Native Python extension; second major integration item. It must be tested with the actual ALSA hardware. |
| FluidSynth | Upstream `fluidsynth` | Enable ALSA output only; omit Jack, PulseAudio, DBus, PortAudio, readline, and file-rendering features unless testing proves a need. | Moderate C++/GLib dependency; not a boot blocker if synth mode is lazy-initialized later. |
| `pyfluidsynth` | No upstream recipe found in the current package tree | Add a pinned project recipe or vendor the binding after verifying its module/API against the selected FluidSynth version. | Usually a thin binding, but exact library loading and version compatibility require a target test. |
| Soundfont | Upstream `fluid-soundfont` | Include it and add an image-level compatibility symlink from the code's expected `/usr/share/sounds/sf2/FluidR3_GM.sf2` to Buildroot's installed `/usr/share/soundfonts/FluidR3_GM.sf2`. | The code’s hard-coded path otherwise prevents synth startup. This is an image migration change, not an app change. |
| ALSA and `amixer` | Upstream `alsa-lib`, `alsa-utils` with `amixer` | Enable `amixer`, ALSA mixer and PCM support, and the actual target card driver. Validate the current `-c 0` and `PCM` assumptions. | Small userspace cost. Incorrect card/control naming is a functional blocker. |
| GPIO | Upstream `python-rpi-gpio` (ARM/AArch64) | Enable it and kernel GPIO/gpiomem support; start the first image as root if necessary, then restrict access only after validating device permissions. | Low image cost; hardware and `/dev/gpiomem` behavior need target validation. |
| Local media | VLC plus pygame/SDL_mixer MP3 support; WAV is also used | Include and test MP3 decode in both audio paths, not only VLC. Current content is MP3 plus a few WAV files. | Media itself (~307 MB in the repository) dominates storage more than the basic OS. |
| Online radio | Kernel Wi-Fi driver/firmware, `wpa_supplicant`, DHCP client, resolver, and VLC HTTP support | Bring networking up asynchronously; never make player start depend on DHCP, DNS, NTP, or Internet reachability. | Wi-Fi firmware/association time should be outside the local-function critical path. |
| SSH for service/development | Optional Dropbear or OpenSSH | Include Dropbear only in a development/recovery image; do not make it a local-player boot dependency. | Convenience/security trade-off, not a player requirement. |

### What dominates size, boot, and integration risk

**Integration complexity:** libVLC and the three missing Python bindings/packages are the primary risks. `pygame` needs a cross-built native extension and validated SDL_mixer MP3 output. `python-vlc` and `pyfluidsynth` may be simple to package, but require pinned versions and target ABI testing.

**Image size:** the existing media collection is the largest known payload. libVLC, Python, SDL/pygame, FluidSynth/GLib, codecs, and a soundfont are the next largest contributors. The boot FAT partition and BusyBox base are comparatively small.

**Boot time:** package size matters mostly through storage I/O and process/library startup. Firmware, kernel, SD-card performance, driver initialization, filesystem mounting, and waiting for network/services dominate cold boot more than the small application source itself. VLC remains worthwhile to remove later for image complexity; it is not safe to assume it alone explains the current 45 seconds.

## VLC decision: retain first, replace later only with a benchmarked design

**Initial migration:** retain libVLC and `python-vlc`. This avoids changing music, radio, pause/resume, next/previous, and end-of-track behavior while the OS, audio card, GPIO, and filesystem are being proven.

**Later option:** VLC is likely heavyweight for a headless appliance playing local MP3 and HTTP MP3 radio. A smaller dedicated playback backend (for example, a controlled `mpg123` process for MP3/HTTP, or a deliberately small GStreamer design) could materially reduce image complexity and eliminate libVLC callback behavior. It would also require replacement semantics for seeking/pause, track completion, station failures, subprocess lifecycle, and error handling. Do not combine that rewrite with the OS migration.

**Decision gate:** measure a Buildroot image retaining VLC first. Consider a playback replacement only if it produces a material, measured gain in image size, startup time, or reliability and preserves every existing behavior in a hardware regression test.

## Proposed filesystem, packaging, and update layout

```text
microSD
├── boot (FAT, Raspberry Pi firmware, kernel, DTBs, cmdline/config)
└── rootfs (ext4 mounted read-only, or SquashFS where validated)
    ├── /home/dnl/RasPlayer/
    │   ├── RasPlayer.py and player modules
    │   └── Sounds/                 # initial image: immutable, same paths
    ├── /usr/lib, /usr/bin          # Buildroot packages and Python runtime
    ├── /usr/share/soundfonts/      # Buildroot soundfont package
    ├── /run/rasplayer/             # tmpfs: PID, heartbeat, volatile status
    ├── /tmp                        # tmpfs
    └── /var/log                    # tmpfs or rate-limited volatile log
```

**Initial image:** package `/home/dnl/RasPlayer` and its `Sounds/` tree directly into the immutable root filesystem via the project overlay/package. This preserves every relative path and guarantees local media availability before network is ready.

**Future content updates:** if songs must change independently of OS releases, use a separately mounted, integrity-checked data partition or signed update bundle and mount/bind it at `/home/dnl/RasPlayer/Sounds`. Do not make a network mount a prerequisite for boot. This is optional; the current application has no writable state requiring a data partition.

**Read-only root:** recommended for the appliance release. Mount the root filesystem read-only; use tmpfs for `/run`, `/tmp`, and nonessential logs. Persist only intentionally designed data (for example, a small error counter or configuration) in a separate writable partition with bounded writes and atomic updates. Keep a serial console or recovery image for diagnostics. A development image may use writable ext4 to speed iteration, but it is not the reliability target.

## Startup, supervision, and recovery architecture

Use BusyBox init rather than systemd for the appliance image. A custom init script starts the player manager as soon as essential mounts, devtmpfs, the ALSA device, and GPIO access are available. It must not wait for Wi-Fi, DHCP, DNS, NTP, SSH, or an interactive login.

```text
firmware -> minimal kernel + built-in essential drivers -> BusyBox init
  -> mount read-only root + tmpfs /run
  -> start hardware-watchdog service
  -> start rasplayer-manager
       -> start player child in /home/dnl/RasPlayer
       -> restart child on exit with bounded backoff
       -> later: require monotonic health heartbeat from player
       -> on missed heartbeat: terminate, then SIGKILL/restart child
       -> if manager itself stops servicing watchdog: hardware reset
  -> start Wi-Fi association/DHCP in parallel (optional, non-blocking)
```

### Crash and hang recovery

- **Crash recovery, migration phase:** the manager waits for the child, logs an exit reason, and restarts it with bounded exponential backoff to prevent a rapid failure loop. This replaces the useful portion of `systemd Restart=always` without pulling systemd into the appliance image.
- **Hang recovery, later stability phase:** add a very small application heartbeat that updates a monotonic timestamp in `/run/rasplayer/heartbeat` only after its control loop remains responsive. The manager restarts the child if that timestamp is stale. Process existence alone is not sufficient to detect a hang.
- **Whole-system recovery:** enable the Pi hardware watchdog early. The manager or a small watchdog helper kicks `/dev/watchdog` only while the application health policy is satisfied. If PID 1/manager/kernel userspace stops progressing, the hardware watchdog resets the board. Select a timeout long enough for normal cold startup but short enough for unattended recovery (to be tuned from measurements).

**Raspberry Pi 3B+ watchdog:** the board uses BCM2837B0-class hardware and the Linux BCM2835 watchdog driver is the relevant kernel watchdog family. Enable and test the kernel watchdog (`CONFIG_BCM2835_WDT`) on the actual target. Bootloader watchdog continuity features documented for newer Pi generations must not be assumed for the Pi 3B+; the first target test must prove when watchdog coverage begins.

## Network behavior

Local player readiness is the priority:

1. Start GPIO, ALSA, and the player manager before Wi-Fi setup completes.
2. Start `wpa_supplicant`/association and DHCP independently in the background. Configure bounded retries and backoff.
3. Do not use `network-online`/equivalent dependencies for the player service.
4. Online-radio mode may attempt playback only when selected; VLC/network errors must be time-bounded and return control to the UI. This final requirement needs a later application stability change because current behavior is delegated to VLC.
5. Make NTP, DNS, SSH, and remote update services optional and noncritical; omit them from the appliance image unless there is a concrete requirement.

## Boot-time target

Define the metric before optimizing: elapsed time from power application to **local buttons accepted and local startup/sample audio playable**, measured at the device.

- **Realistic initial Buildroot target:** 8–12 seconds on a Pi 3B+ with healthy power, a good SD card, the retained Python/VLC/pygame stack, minimal kernel/userspace, and no network wait. The live application alone took about 7.1 seconds to reach loaded startup samples while the Pi was throttled, so the earlier 6–10 second estimate was too optimistic as a baseline commitment.
- **Updated application evidence:** the lazy-startup refactor reduced Raspberry Pi OS kernel-relative local readiness to 18.7–18.8 seconds (about 1.3–1.5 seconds faster). First-use MUSIC/ONLINE/SYNTH initialization now occurs after `LOCAL_READY`; details are in `docs/pi-boot-optimization.md`.
- **Ambitious optimized target:** 3–5 seconds is technically plausible only for local readiness after application startup work as well as OS tuning. It requires removing most of the measured eager-import cost, then tuning firmware/kernel, built-in essential drivers, rootfs/image format, and SD-card I/O. It must exclude Wi-Fi association and Internet availability from readiness.
- **Not a valid target:** 3–5 seconds to fully associated Wi-Fi, DHCP, DNS, NTP, and usable Internet radio cannot be promised because it depends on RF and network conditions.

Optional optimizations specifically for the 3–5 second goal:

- Choose a fast, known-good SD card and measure it; eliminate boot-time filesystem checks and unnecessary writes.
- Build only Pi 3B+ drivers into the kernel; avoid modules needed before local readiness; remove Bluetooth, HDMI/display, USB services, IPv6, swap, discovery daemons, and unused filesystems only after confirming hardware requirements.
- Use a minimal BusyBox init and start only watchdog, player manager, and non-blocking Wi-Fi. Avoid systemd for this appliance target.
- Keep the root filesystem immutable and compact; evaluate compressed SquashFS versus read-only ext4 based on measured decompression/I/O, not assumptions.
- In a later app change, make heavyweight mode-specific initialization lazy (especially FluidSynth) and remove fixed sleeps where safe. Do not change user-visible startup behavior without measurements.
- After a fully working migration, benchmark a VLC replacement separately.

## A, B, and C: change classification

| Class | Changes | When |
| --- | --- | --- |
| **A. Required to migrate the existing app** | Create Buildroot external tree/defconfig/board config; package current files and sounds at `/home/dnl/RasPlayer`; enable kernel/firmware/audio/GPIO/network requirements; add recipes or vendor pinned `python-vlc`, pygame, and pyfluidsynth; create FluidR3 compatibility symlink; replace systemd unit with BusyBox init manager; validate exact ALSA card/control and GPIO permissions. | First working image. |
| **B. Recommended later for application stability** | Serialize events and mode transitions; move blocking work out of GPIO callbacks; add explicit player/audio teardown; validate media before indexing; give radio failures timeouts/recovery; add application health heartbeat and diagnostics; add hardware regression/stress tests. | After baseline functionality is proven. |
| **C. Optional optimizations for 3–5 seconds** | Kernel/firmware/init pruning, essential driver selection, rootfs/SD optimization, parallel non-blocking network, lazy mode initialization, and separately benchmark/replace VLC if justified. | Only after a measured baseline. |

## Reproducible Buildroot deliverables

Keep all project-owned build inputs in this repository, preferably under `buildroot/` (or a clearly named external tree), without committing Buildroot build outputs:

```text
buildroot/
├── README.md                         # host prerequisites and exact build command
├── buildroot.version                 # pinned release/tag + verified commit/hash
├── external.desc
├── Config.in
├── external.mk
├── configs/rasplayer_pi3bplus_defconfig
├── board/rasplayer-pi3bplus/
│   ├── kernel.config
│   ├── rootfs-overlay/
│   │   ├── home/dnl/RasPlayer/        # application and initial media
│   │   └── etc/init.d/S??rasplayer
│   ├── users.txt
│   ├── post-build.sh
│   ├── post-image.sh
│   └── genimage.cfg
└── package/
    ├── python-vlc/
    ├── python-pygame/
    └── python-pyfluidsynth/
```

Required reproducibility controls:

- Pin Buildroot, Linux/kernel, firmware, all project package versions, source URLs, hashes, patches, and the cross-toolchain choice.
- Commit the defconfig, kernel/BusyBox configuration, rootfs overlay, init scripts, image-generation configuration, users/device permissions, and package recipes.
- Decide whether media is versioned in Git, supplied by a versioned/private artifact, or placed in a versioned update bundle; record hashes and licensing/provenance. The current repository’s `.gitignore` makes future media tracking inconsistent and needs an explicit policy before image release.
- Generate a complete SD-card image (boot FAT plus rootfs) with `genimage` or equivalent, then publish its checksum, build manifest, and test report. Do not write it to `F:\` until a separate explicit approval/task.
- Run Buildroot `legal-info` and preserve the resulting license/source manifest for all included packages and media where applicable.
- Build in a controlled container/VM or documented Linux host; cache downloads but do not rely on unpinned `latest` sources.

## Exact implementation phases

1. **Capture the current Pi baseline.** Collect boot timeline, `rasplayer.service`, package versions, ALSA topology, kernel/config/firmware, enabled services, GPIO/electrical details, logs, and reproducible hang symptoms. Establish a cold-boot measurement definition.
2. **Prove the toolchain and dependency recipes.** On a development Linux host/VM, pin Buildroot; create the external tree; build package-only smoke images with Python, RPi.GPIO, ALSA, VLC, pygame, FluidSynth, soundfont, and the three project Python packaging paths.
3. **Build a hardware-minimal baseline image.** Add Pi 3B+ boot/kernel/firmware, Wi-Fi support, exact audio support, BusyBox init, and the application/media under `/home/dnl/RasPlayer`; retain application source behavior. Generate an image artifact only—do not write an SD card yet.
4. **Functional hardware validation.** Write only to a deliberately approved test card in a separate task. Validate every GPIO, local media mode, system/volume sounds, synth, online radio with and without network, repeated restarts, and power cycling.
5. **Add supervision and immutable filesystem.** Introduce the manager, crash restart/backoff, watchdog driver/helper, read-only root, tmpfs logs, and recovery/diagnostic access. Validate intentional crash, blocked child, and power-loss scenarios.
6. **Make application stability changes.** Implement the class-B changes with tests and hardware stress evidence. Add heartbeat-based hang recovery only after the app can report meaningful liveness.
7. **Optimize from measurements.** Reduce boot path, tune kernel/filesystem/SD choices, parallelize network, then reassess VLC replacement. Accept 3–5 seconds only if repeatable over cold boots and all local functionality is present.
8. **Release process.** Produce versioned images, checksums, provenance/legal report, rollback/recovery instructions, and a documented content-update workflow.

## Information still required from the existing Pi

Before phase 2/3, obtain the items already listed in `docs/operations-and-platform.md`, with special priority on:

1. Exact Raspberry Pi OS release, 32/64-bit architecture, kernel/firmware, boot config/cmdline, microSD model/class, partition layout, and measured timestamps from power-on through local readiness.
2. Actual `rasplayer.service`, launch user/groups/environment, installed package and Python/pip versions, and any `/etc/asound.conf`, `.asoundrc`, or custom udev/boot configuration.
3. `aplay -l`, `amixer -c 0 scontrols`, `ls -l /dev/gpiomem /dev/mem`, and the precise audio hardware/driver path.
4. Exact GPIO wiring, ultrasonic sensor model/level shifting, button circuits, LED, amplifier/DAC, Wi-Fi requirements, and Bluetooth/USB/SSH requirements.
5. Logs and reproducible sequences for hangs, including whether the process remains alive, `journalctl`, `dmesg`, under-voltage flags, and CPU/memory/audio errors.
6. Whether content must be updateable independently, expected field-update/recovery method, and requirements for persistent logs/configuration.

## Sources used for Buildroot planning

- [Buildroot manual: init systems and project customisation](https://buildroot.org/downloads/manual/manual.html)
- [Buildroot current package tree](https://github.com/buildroot/buildroot/blob/master/package/Config.in) (package availability is version-sensitive; pin before implementation)
- [Buildroot VLC package recipe](https://github.com/buildroot/buildroot/blob/master/package/vlc/vlc.mk)
- [Buildroot FluidSynth package configuration](https://github.com/buildroot/buildroot/blob/master/package/fluidsynth/Config.in)
- [Buildroot RPi.GPIO package configuration](https://github.com/buildroot/buildroot/blob/master/package/python-rpi-gpio/Config.in)
- [Raspberry Pi boot/watchdog configuration documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html)
- [Linux BCM2835 watchdog driver](https://github.com/torvalds/linux/blob/master/drivers/watchdog/bcm2835_wdt.c)
