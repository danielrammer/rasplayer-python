# RasPlayer Buildroot image

This external tree targets the Raspberry Pi 3B+ (64-bit) and preserves the
application path `/home/dnl/RasPlayer`. Buildroot is pinned in
`buildroot.version` (2024.02.9, commit
`d37527ba498c34508b9f3fede34135686c94581e`).

## WSL2 build

Build on WSL2's native ext4 filesystem, not directly below `/mnt/c` or
`/mnt/d`: host-package builds are not reliable on DrvFS. Install host
prerequisites (`cpio`, `unzip`, `rsync`, `bc`, `file`, Python, Perl), copy the
repository to a Linux path, clone the pinned Buildroot release, then run:

```sh
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
work="$HOME/rasplayer-build"
repo="$work/repo"
make -C "$work/buildroot-src" BR2_EXTERNAL="$repo/buildroot" \
  O="$work/output" rasplayer_pi3bplus_defconfig
make -C "$work/buildroot-src" O="$work/output" -j2
```

The intended artifact is `$HOME/rasplayer-build/output/images/sdcard.img`.
This repository does not
write images to physical drives. The initial image must be hardware-tested
before enabling immutable-root and hardware-watchdog production policies.

The image uses an MBR partition table with 1 MiB alignment: a 64 MiB bootable
FAT partition followed by a 768 MiB ext4 root partition. The boot partition
contains the AArch64 `Image`, Pi 3/3B+ DTBs, firmware, overlays, `cmdline.txt`,
and the project-owned `config.txt`.

The root filesystem routes default ALSA playback and mixer control to card 0,
matching the measured Raspberry Pi baseline. BusyBox init starts Wi-Fi
asynchronously through `S41wifi` and starts the supervised player through
`S50rasplayer`; the player working directory is `/home/dnl/RasPlayer`.
`S41wifi` explicitly loads the modular Pi Wi-Fi driver, waits for `wlan0`, and
retries association/DHCP failures without gating local readiness. `S50rasplayer`
loads the GPIO memory device, supplies explicit musl-safe VLC/SDL runtime
settings, records child exits and heartbeat kills, and retains the existing
bounded-backoff restart policy.

SDL2_mixer is built with its bundled MP3 decoder because pygame loads the
system and instrument MP3 files directly. The pyFluidSynth binding carries a
minimal Linux soname fallback for musl targets without `ldconfig`; the
application's existing `/usr/share/sounds/sf2/FluidR3_GM.sf2` compatibility
path remains present.

The instrumented measurement image records kernel-uptime timestamps around
each BusyBox init script, ALSA availability, RasPlayer/Python launch, mpg123,
and `LOCAL_READY`. After readiness it saves the report as `boot-timeline.txt`
on the FAT boot partition and retains the previous two reports. See
`docs/buildroot-boot-instrumentation.md` for the physical test and offline
retrieval procedure.

A later background snapshot is also written as `rasplayer-diagnostics.txt` on
the FAT partition. It captures post-readiness application, supervisor, GPIO,
module, and networking state without placing networking on the startup path.

The media tree is deployment content. If `Sounds/` is absent from this
checkout, the image cannot provide the application's local media and the
missing content must be supplied as a versioned build input before release.
The build fails rather than creating an image without `Sounds/`.

The image contains a credential-free `/etc/wpa_supplicant.conf`. Before first
boot, copy locally prepared `wifi.network` and `dnl_authorized_keys` files to
the top level of the flashed FAT partition. `S40provision` imports them, then
`S41wifi` starts association/DHCP asynchronously; Dropbear accepts key-only
SSH for user `dnl`. The files are never committed. See
`docs/buildroot-remote-development.md` for the one-time procedure and log/IP
discovery details.
