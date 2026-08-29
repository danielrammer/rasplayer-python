# Buildroot Wi-Fi and SSH provisioning

The development image keeps network startup asynchronous. BusyBox init starts
RasPlayer without waiting for Wi-Fi association, DHCP, DNS, or SSH. Wi-Fi
credentials and the SSH public key are supplied locally on the readable FAT
boot partition; neither is stored in Git or in the generated image before
provisioning.

## One-time provisioning before first boot

1. Generate or select an SSH key on the development computer. For a dedicated
   key, use `ssh-keygen -t ed25519 -f ~/.ssh/rasplayer_buildroot_ed25519` and
   keep the private key on the development computer.
2. Prepare two local text files in a temporary directory (not the repository):

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
   `wifi.network` and `dnl_authorized_keys` into its top-level directory. Do
   not copy the private key. Safely eject the card.
5. On the first boot, `S40provision` imports the files, creates user `dnl`
   (UID/GID 1000, `/home/dnl`, `/bin/sh`), installs the key as
   `/home/dnl/.ssh/authorized_keys`, and rebuilds `/etc/wpa_supplicant.conf`
   from the base configuration plus the network block. The account has a
   locked password; SSH access is key-only.

The provisioning files remain on the FAT partition as local secrets. To
deprovision, remove `wifi.network` and `dnl_authorized_keys` from the FAT
partition and reboot. The next boot restores the credential-free base Wi-Fi
configuration and leaves SSH without an authorized key.

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

No network connection is required to retrieve the boot report: power off after
waiting at least 30 seconds past the startup sound, remove the card, and read
the FAT files on the development computer.
