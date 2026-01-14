#!/bin/bash
echo "Copying files to Pi"

rsync -av RasPlayer.py SoundPlayer.py OnlinePlayer.py SamplePlayer.py MusicPlayer.py dnl@192.168.0.70:/home/dnl/RasPlayer

./restartPlayer.sh