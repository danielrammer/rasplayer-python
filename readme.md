# installed packages
sudo apt-get install xdotool
sudo apt-get install xvfb

# but time optimization
## disabled bluetooth
added dtoverlay=disable-bt in /boot/config.txt

### disabled uart
sudo systemctl disable hciuart

## turn of GUI
### disalbe graphical target
[Failed]systemctl enable muli-user.target -> enables what was known as runlevel 3
[No effect?]systemctl disable graphical.target -> disables GUI
#### re enable
systemctl start graphical.target
## sudo raspi-config
System Options -> Boot / Auto Login -> B1 Console

## turning off further services
sudo systemctl disable keyboard-setup.service
sudo systemctl disable dphys-swapfile.service

## dhcp 
added in /etc/dhcpcd.conf
    noarp
    ipv4only
    noipv6

# save power
https://raspberrypi-guide.github.io/electronics/power-consumption-tricks#turn-of-hdmi-output