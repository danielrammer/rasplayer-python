#!/bin/bash

DELETE="--delete"

if [ "$1" = "--keep" ]; then
    DELETE=""
fi

rsync -av $DELETE \
  --exclude='SystemSoundsProject/' \
  -e "ssh -i ~/.ssh/rasplayer_buildroot_ed25519" \
  Sounds/ dnl@192.168.0.70:/home/dnl/RasPlayer/Sounds/