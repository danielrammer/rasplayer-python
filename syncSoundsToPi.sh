#!/bin/bash

rsync -av --exclude=SystemSoundsProject \
  -e "ssh -i ~/.ssh/rasplayer_buildroot_ed25519" \
  Sounds dnl@192.168.0.70:/home/dnl/RasPlayer