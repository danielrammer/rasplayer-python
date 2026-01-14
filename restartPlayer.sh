#!/bin/bash
echo "Restarting RasPlayer on Pi"
echo "Add IP address as first argument if different from default (192.168.0.70)"
echo "Using IP address: ${1:-192.168.0.70}"

IP="${1:-192.168.0.70}"
ssh dnl@$IP "sudo systemctl restart rasplayer.service"