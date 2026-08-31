# Buildroot Wi-Fi and SSH provisioning

The development image keeps network startup asynchronous. BusyBox init starts
RasPlayer without waiting for Wi-Fi association, DHCP, DNS, or SSH. Wi-Fi
credentials, the SSH public key, and the release-signing public key are
supplied locally on the readable FAT boot partition; none is stored in Git or
in the generated image before provisioning. The signing private key never
leaves the development machine.

## One-time provisioning before first boot

1. Generate or select an SSH key on the development computer. For a dedicated
   key, use `ssh-keygen -t ed25519 -f ~/.ssh/rasplayer_buildroot_ed25519` and
   keep the private key on the development computer.
2. Prepare the Wi-Fi and SSH files in a temporary directory (not the
   repository), and create/verify the separate release-signing pair as
   described in `docs/buildroot-ssh-development.md`:

   `wifi.network`:

   ```text
   network={
       ssid="YOUR_SSID"
       psk="YOUR_WIFI_PASSPHRASE"
   }
   ```

   `dnl_authorized_keys`: one complete OpenSSH public-key line, copied from
   `rasplayer_buildroot_ed25519.pub`.

3. Flash `sdcard.img` to the approved test card. Do not boot it yet.
4. Mount the card's first (FAT) partition on the development computer and copy
   `wifi.network`, `dnl_authorized_keys`, and
   `rasplayer-update-public.pem` into its top-level directory. Do not copy
   either private key. Safely eject the card.
5. On the first boot, `S40provision` imports the files, creates user `dnl`
   (UID/GID 1000, `/home/dnl`, `/bin/sh`), installs the key as
   `/home/dnl/.ssh/authorized_keys`, and rebuilds `/etc/wpa_supplicant.conf`
   from the base configuration plus the network block. The account has a
   locked password; SSH access is key-only.

The provisioning files remain on the FAT partition as local inputs. To
deprovision network/SSH access, remove `wifi.network` and
`dnl_authorized_keys` and reboot. Removing
`rasplayer-update-public.pem` also removes the signed-deployment trust anchor
on the next provisioning pass; retain it for normal recovery and updates.

## Connection and discovery

Wi-Fi association and DHCP run in a background worker from `S41wifi`; they do
not delay RasPlayer or `LOCAL_READY`. The image hostname is `rasplayer`.
The worker explicitly loads `brcmfmac`, waits for `wlan0`, then starts
`wpa_supplicant` and `udhcpc`. Module, interface, or daemon failures are logged
and retried with bounded backoff; the local player does not wait for a lease.
After DHCP succeeds, the worker records the hostname, interface, lease address,
router, IPv4 addresses and routes in:

- `/run/rasplayer/network.status` (current boot)
- `/var/lib/rasplayer/logs/rasplayer-network.log` (persistent root filesystem)
- `network-status.txt` on the FAT boot partition (latest lease, no password)

Connect with the discovered address, for example:

```sh
ssh -i ~/.ssh/rasplayer_buildroot_ed25519 dnl@<address>
```

The unprivileged development account can control only the RasPlayer service
through the installed setuid-root helper:

```sh
rasplayer-service status
rasplayer-service stop
rasplayer-service start
rasplayer-service restart
```

For an isolated HC-SR04 wiring check, stop RasPlayer before using the one
additional fixed diagnostic action:

```sh
rasplayer-service stop
rasplayer-service ultrasonic-test
rasplayer-service start
```

The diagnostic uses `/dev/gpiomem` directly as root with BCM trigger GPIO 14
and echo GPIO 15. It prints the initial echo state and ten measurements, each
with a bounded `ECHO HIGH`/`ECHO LOW` timeout or pulse duration and calculated
distance. It restores both pins' previous function-select state on normal,
error, or signal exit. A shared service-control lock prevents RasPlayer from
starting during the diagnostic. No Python interpreter or caller-selected
command is involved.

The helper accepts only those five exact actions, only from UID 1000 (`dnl`),
and executes only `/etc/init.d/S50rasplayer` with a fixed environment. It does
not provide a shell or general root command execution.

Because RasPlayer executes as root, the image keeps `/home/dnl/RasPlayer` and
its Python code root-owned and non-writable. Otherwise editing an imported
Python file followed by a supervised restart would itself be unrestricted root
execution. `/home/dnl/work` remains owned by `dnl` for uploads and development
artifacts, and `/home/dnl/RasPlayer/Sounds` remains owned by `dnl` for media
synchronization.

Signed SSH deployment adds the fixed `deploy` and `rollback` actions. See
`docs/buildroot-ssh-development.md` for the separate offline release key,
atomic versioned releases, automatic health rollback, and the boundary between
SSH-deployable application changes and image-only platform changes.

`S50dropbear` also runs outside the local-startup critical path. After
`LOCAL_READY` it validates, or atomically creates, a device-unique Ed25519 host
key at `/etc/dropbear/dropbear_ed25519_host_key`, then starts Dropbear with that
key explicitly. Host-key creation and SSH connection failures are written to
`/var/lib/rasplayer/logs/dropbear-supervisor.log`; the worker supervises and
restarts Dropbear without blocking RasPlayer. The board finalization step
replaces Buildroot's `/etc/dropbear -> /var/run/dropbear` link with an empty
`0700` directory on the writable ext4 root, so the generated key persists
across boots. Runtime setup validates that layout, has a logged volatile
fallback for read-only media, and retries failures asynchronously.

There is no mDNS dependency; use `network-status.txt`, the DHCP/router lease
table, or the local display/console to discover the address reliably.

## Logs

The existing boot instrumentation remains enabled. After `LOCAL_READY`, the
image writes `/var/log/boot-timeline.txt`, including kernel `dmesg`, all
timestamped init/Python/mpg123 markers, ALSA state, the RasPlayer log captured
at snapshot time, and network status. It copies that report to the FAT boot
partition as `boot-timeline.txt` and retains the previous two reports. The
ongoing application log is `/var/lib/rasplayer/logs/rasplayer.log`; it is persistent and
bounded by one rotated `.1` file.

The supervisor also keeps `/var/lib/rasplayer/logs/rasplayer-supervisor.log`,
including child exit status and heartbeat timeouts. Approximately 25 seconds
after the initial boot-timeline snapshot, and immediately after supervised
child failures, a combined report is saved to:

- `/var/lib/rasplayer/logs/rasplayer-diagnostics.txt` on the ext4 root;
- `rasplayer-diagnostics.txt` on the readable FAT boot partition.

That report contains process/module state, GPIO and network device presence,
boot events, bounded tails of the application/supervisor/network logs, and a
kernel-log tail. It contains no provisioned Wi-Fi password or SSH private key.
The report also includes Dropbear host-key metadata, kernel entropy state, and
the bounded tail of `dropbear-supervisor.log` (never the private key itself).

No network connection is required to retrieve the boot report: power off after
waiting at least 30 seconds past the startup sound, remove the card, and read
the FAT files on the development computer.
