#!/bin/bash
set -e

HOST="dnl@192.168.0.70"
KEY="$HOME/.ssh/rasplayer_buildroot_ed25519"
REMOTE="/home/dnl/RasPlayer/Sounds"

echo "Removing old sounds..."
ssh -i "$KEY" "$HOST" \
  "rm -rf '$REMOTE'/*"

echo "Uploading sounds..."
tar --exclude='Sounds/SystemSoundsProject' -cf - Sounds | gzip | \
ssh -i ~/.ssh/rasplayer_buildroot_ed25519 dnl@192.168.0.70 \
  "gzip -d | tar -xf - -C /home/dnl/RasPlayer"

echo "Done."