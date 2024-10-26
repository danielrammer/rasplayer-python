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