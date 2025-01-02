#!/bin/bash
echo "Copying files to Pi"
# RC=1
# while [[ $RC -ne 0 ]]
# do
#     echo "Trying to copy files to Pi"
rsync -av RasPlayer.py SoundPlayer.py OnlinePlayer.py SamplePlayer.py MusicPlayer.py dnl@192.168.0.251:/home/dnl/RasPlayer
#     RC=$?
# done