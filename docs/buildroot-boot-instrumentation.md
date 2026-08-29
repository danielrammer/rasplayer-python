# Buildroot boot timeline instrumentation

## Purpose and clock

The instrumented image records the first physical Buildroot boot path without
requiring Wi-Fi, SSH, a real-time clock, or systemd. All `BOOTTRACE` and
`STARTUP` timestamps are seconds since Linux kernel monotonic time zero.
Kernel messages retain their normal bracketed timestamps because the kernel
has `CONFIG_PRINTK_TIME=y` and the boot command line explicitly includes
`printk.time=1`.

Linux cannot timestamp the Raspberry Pi firmware stage because the monotonic
clock begins at kernel entry. For the same boot, subtract the logged
`rasplayer_mpg123_process_started` time from the physical power-on-to-audible
measurement to estimate the combined pre-kernel firmware interval plus the
small decoder/device-to-audible latency. A trustworthy direct firmware/kernel
boundary would require an externally timestamped serial or GPIO trace.

Do not attach a serial adapter to GPIO14/15 for this test: those BCM pins are
assigned to the ultrasonic trigger/echo hardware by `GPIO-Mapping.md`. The
first instrumented image incorrectly named `ttyAMA0` as a console; current
images disable that UART so it cannot retain the application pins.

## Recorded boundaries

The image records:

- timestamped kernel initialization and `/sbin/init` launch in `dmesg`;
- `userspace_rcS_begin` and `userspace_rcS_end`;
- start, end, exit status, and therefore duration of every `S??` init script;
- first userspace observation of `/dev/snd/pcmC0D0p`;
- RasPlayer init-script, manager, Python-launch, and child-start boundaries;
- Python entry, minimum imports, GPIO readiness, mpg123 launch/process/validation,
  audio readiness, callback registration, and `LOCAL_READY`;
- the ALSA card list at `LOCAL_READY`.

After `LOCAL_READY`, a background helper writes `/var/log/boot-timeline.txt`,
mounts the boot FAT briefly, and copies the report to `boot-timeline.txt`.
The previous two reports are retained as `boot-timeline-2.txt` and
`boot-timeline-3.txt`. This persistence occurs after the measured readiness
boundary and therefore does not delay the startup sound.

## Physical measurement procedure

1. Flash the instrumented `sdcard.img` to the same test card using the normal
   separately approved flashing procedure.
2. Keep power supply, amplifier, speakers, GPIO hardware, SD card, and Ethernet
   cable state identical to the first ~16-second test. Record whether Ethernet
   is connected. Do not provision Wi-Fi yet.
3. Remove power for at least ten seconds. Start a stopwatch or continuous phone
   video at power application and mark the first audible startup sound.
4. Leave the Pi powered for at least 30 seconds after the sound. This gives the
   post-readiness report time to be copied and synced to the FAT partition.
5. Repeat for three cold boots. Wait at least 30 seconds after the sound on each
   run; the FAT partition retains the newest three reports.
6. Power off, remove the card, and insert it in the development computer. Open
   the ordinary FAT boot partition and copy `boot-timeline.txt`,
   `boot-timeline-2.txt`, and `boot-timeline-3.txt`. No Linux ext4 support or
   network connection is needed.
7. Record the three physical power-on-to-audible values alongside the three
   files. Do not infer firmware time by pairing a report with a different boot.

If no timeline file appears, the fallback report remains at
`/var/log/boot-timeline.txt` in the ext4 root filesystem. Inspecting that file
requires mounting the second partition on Linux or reading it with `debugfs`.

## Current delay candidates to measure, not optimize yet

The generated init order is `S01seedrng`, `S01syslogd`, `S02klogd`,
`S02sysctl`, `S40network`, `S41wifi`, `S50dropbear`, then `S50rasplayer`.
Every earlier script is synchronous from RasPlayer's perspective.

- `S40network` runs `ifup -a` for `eth0`. Its generated interface contains
  `wait-delay 15`, which applies only if the Ethernet interface itself is
  absent. With the interface present but unplugged, BusyBox DHCP uses
  `-t1 -A3 -b`; the trace will show the actual cost.
- `S41wifi` runs despite the credential-free configuration and invokes
  `udhcpc -b`. Default discovery retries may take time before it backgrounds.
- `S50dropbear` precedes RasPlayer and uses runtime host-key generation (`-R`),
  which may make the first writable-image boot slower than later boots.
- The kernel has built-in BCM2835 audio and USB audio support, while Wi-Fi and
  HDMI codec support include loadable modules. Timestamped kernel messages will
  show driver probing and any device timeout evidence.
- The command line contains the required `rootwait`, but no explicit boot delay
  or initcall-debug option. Firmware configuration likewise contains no
  `boot_delay` setting.

These are inspection findings, not optimization conclusions. Compare three
cold traces before changing service order, DHCP behavior, kernel drivers, or
firmware options.
