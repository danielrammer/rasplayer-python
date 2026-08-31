#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 dnl@HOST BUNDLE_DIR [SSH_IDENTITY]" >&2
    exit 2
fi

target=$1
bundle=$2
identity=${3:-}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "${script_dir}/../.." && pwd)
generic_sound=${repo}/Sounds/System/0/generic.mp3
[ -f "${bundle}/manifest" ] && [ -f "${bundle}/signature" ] && \
    [ -d "${bundle}/payload" ] || { echo "Invalid bundle directory" >&2; exit 1; }
[ -f "${generic_sound}" ] || { echo "Missing ${generic_sound}" >&2; exit 1; }

install_generic_sound() {
    install_identity=$1
    if [ -n "${install_identity}" ]; then
        scp -O -i "${install_identity}" "${generic_sound}" \
            "${target}:/home/dnl/work/generic.mp3.upload"
        ssh -i "${install_identity}" "${target}" \
            'cmp /home/dnl/work/generic.mp3.upload /home/dnl/RasPlayer/Sounds/System/0/vol-down.mp3 && mv /home/dnl/work/generic.mp3.upload /home/dnl/RasPlayer/Sounds/System/0/generic.mp3'
    else
        scp -O "${generic_sound}" \
            "${target}:/home/dnl/work/generic.mp3.upload"
        ssh "${target}" \
            'cmp /home/dnl/work/generic.mp3.upload /home/dnl/RasPlayer/Sounds/System/0/vol-down.mp3 && mv /home/dnl/work/generic.mp3.upload /home/dnl/RasPlayer/Sounds/System/0/generic.mp3'
    fi
}

if [ -n "${identity}" ]; then
    install_generic_sound "${identity}"
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O -i "${identity}" "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O -i "${identity}" "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
else
    install_generic_sound ""
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
fi
