#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 dnl@HOST BUNDLE_DIR [SSH_IDENTITY]" >&2
    exit 2
fi

target=$1
bundle=$2
identity=${3:-}
[ -f "${bundle}/manifest" ] && [ -f "${bundle}/signature" ] && \
    [ -d "${bundle}/payload" ] || { echo "Invalid bundle directory" >&2; exit 1; }

if [ -n "${identity}" ]; then
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O -i "${identity}" "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O -i "${identity}" "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
else
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
fi
