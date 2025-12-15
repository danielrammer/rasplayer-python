# setup
## no DHCP and fixed ip
in `/etc/dhcpcd.conf`add:

interface wlan0 
static ip_address=192.168.0.251<br>
static routers=192.168.0.1<br>
static domain_name_servers=8.8.8.8

# installed packages
sudo apt-get install mpg123<br>
sudo apt install python3-pip<br>
sudo pip install mpyg321

## for Sampler
pip install pygame

# boot time optimization
use headless installation<br>
**DONT disable `dhcpcd.service`**
## disabled bluetooth
add `dtoverlay=disable-bt` in `/boot/config.txt`

## disabled uart (speed up)
sudo systemctl disable hciuart

## dhcp / speed up<>
add in `/etc/dhcpcd.conf`

#noarp #not used!
ipv4only
noipv6

## check speed
systemd-analyze<br>
systemd-analyze blame

# system service
/etc/systemd/system/rasplayer.service

## service config
[Unit]
Description=mp3 player and web radio
After=multi-user.target
[Service]
Type=simple
Restart=always
ExecStart=/usr/bin/python /home/dnl/RasPlayer/RasPlayer.py
WorkingDirectory=/home/dnl/RasPlayer
[Install]
WantedBy=multi-user.target

## enable and start
sudo systemctl daemon-reload<br>
sudo systemctl enable rasplayer.service<br>
sudo systemctl start rasplayer.service

## analyze
### read log
journalctl -u rasplayer.service -f

### check under voltage
dmesg


# save power (is this useful for LITE installation?)
https://raspberrypi-guide.github.io/electronics/power-consumption-tricks#turn-of-hdmi-output


## turn of GUI (not necessary if installed headless)
ONLY FOR GUI OS 
### disalbe graphical target
[Failed]systemctl enable muli-user.target -> enables what was known as runlevel 3
[No effect?]systemctl disable graphical.target -> disables GUI
#### re enable
systemctl start graphical.target
systemctl enable graphical.target 
## sudo raspi-config
System Options -> Boot / Auto Login -> B1 Console

## turning off further services
sudo systemctl disable keyboard-setup.service
sudo systemctl disable dphys-swapfile.service

## Troubleshooting: ALSA "underrun occurred"

If you see messages like `ALSA lib pcm.c:8545:(snd_pcm_recover) underrun occurred` in the logs when running the player on a Raspberry Pi, this means the audio buffer underflowed (the audio driver ran out of data to play). Common causes and fixes:

- Increase the audio buffer used by the SDL/pygame mixer. In `SamplePlayer.py` we now initialize the mixer once with a larger buffer (default 4096). If underruns persist, try larger values (8192).
- Avoid reinitializing the mixer frequently (call `pygame.mixer.init()` once). Re-inits can cause glitches.
- Use WAV (PCM) files instead of MP3s, or pre-convert MP3s to WAV to avoid real-time decoding overhead.
- Verify CPU/IO load while playing (run `top`/`htop`) — heavy load can cause underruns. Consider closing other processes or raising process priority.
- Test the audio hardware independent of the app using `aplay`:

```bash
aplay -D plughw:0,0 /usr/share/sounds/alsa/Front_Center.wav
journalctl -f | grep -i alsa
```

- If using ALSA device options, you can tune period_size and buffer_size in `~/.asoundrc` or `/etc/asound.conf` (use carefully).
- If you continue to see underruns, experiment with the mixer buffer setting in `SamplePlayer.py` (the `ensure_mixer_initialized` helper) and consider converting samples to uncompressed PCM for lower CPU use.

If you'd like, I can add an automated test script that plays a sample in a loop and checks `journalctl` for underrun messages — tell me and I will create it.

### Underrun test script

There's an included test script `tests/underrun_test.py` that plays a WAV in a loop and optionally tails `journalctl` for the word "underrun".

Example (run on the Raspberry Pi):

```bash
# play sample.wav for 30s with 4096 buffer and check journalctl for underruns
python3 tests/underrun_test.py /path/to/sample.wav --buffer 4096 --duration 30 --check-journal
```

Try increasing `--buffer` to 8192 if you still see messages.

