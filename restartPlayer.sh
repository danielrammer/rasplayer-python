#!/bin/bash
echo "Restarting RasPlayer on Pi"

ssh dnl@192.168.0.70 "sudo systemctl restart rasplayer.service"