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
system_sound_dir=${repo}/Sounds/System/0
system_sounds="generic.mp3 mode-switch.mp3 TurnOn.mp3 vol-down.mp3 vol-max.mp3 vol-up.mp3"
[ -f "${bundle}/manifest" ] && [ -f "${bundle}/signature" ] && \
    [ -d "${bundle}/payload" ] || { echo "Invalid bundle directory" >&2; exit 1; }
for system_sound in ${system_sounds}; do
    [ -s "${system_sound_dir}/${system_sound}" ] || {
        echo "Missing or empty ${system_sound_dir}/${system_sound}" >&2
        exit 1
    }
done

install_system_sounds() {
    install_identity=$1
    if [ -n "${install_identity}" ]; then
        ssh -i "${install_identity}" "${target}" \
            'rm -rf /home/dnl/work/system-sounds.upload && mkdir -p /home/dnl/work/system-sounds.upload'
        scp -O -i "${install_identity}" \
            ${system_sound_dir}/generic.mp3 \
            ${system_sound_dir}/mode-switch.mp3 \
            ${system_sound_dir}/TurnOn.mp3 \
            ${system_sound_dir}/vol-down.mp3 \
            ${system_sound_dir}/vol-max.mp3 \
            ${system_sound_dir}/vol-up.mp3 \
            "${target}:/home/dnl/work/system-sounds.upload/"
        ssh -i "${install_identity}" "${target}" \
            'set -eu; for sound in generic.mp3 mode-switch.mp3 TurnOn.mp3 vol-down.mp3 vol-max.mp3 vol-up.mp3; do test -s "/home/dnl/work/system-sounds.upload/${sound}"; done; mkdir -p /home/dnl/RasPlayer/Sounds/System/0; mv /home/dnl/work/system-sounds.upload/* /home/dnl/RasPlayer/Sounds/System/0/; rmdir /home/dnl/work/system-sounds.upload'
    else
        ssh "${target}" \
            'rm -rf /home/dnl/work/system-sounds.upload && mkdir -p /home/dnl/work/system-sounds.upload'
        scp -O \
            ${system_sound_dir}/generic.mp3 \
            ${system_sound_dir}/mode-switch.mp3 \
            ${system_sound_dir}/TurnOn.mp3 \
            ${system_sound_dir}/vol-down.mp3 \
            ${system_sound_dir}/vol-max.mp3 \
            ${system_sound_dir}/vol-up.mp3 \
            "${target}:/home/dnl/work/system-sounds.upload/"
        ssh "${target}" \
            'set -eu; for sound in generic.mp3 mode-switch.mp3 TurnOn.mp3 vol-down.mp3 vol-max.mp3 vol-up.mp3; do test -s "/home/dnl/work/system-sounds.upload/${sound}"; done; mkdir -p /home/dnl/RasPlayer/Sounds/System/0; mv /home/dnl/work/system-sounds.upload/* /home/dnl/RasPlayer/Sounds/System/0/; rmdir /home/dnl/work/system-sounds.upload'
    fi
}

if [ -n "${identity}" ]; then
    install_system_sounds "${identity}"
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O -i "${identity}" "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O -i "${identity}" "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh -i "${identity}" "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
else
    install_system_sounds ""
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.upload && mkdir -p /home/dnl/work/rasplayer-update.upload/payload'
    scp -O "${bundle}/manifest" "${bundle}/signature" \
        "${target}:/home/dnl/work/rasplayer-update.upload/"
    scp -O "${bundle}/payload/"* \
        "${target}:/home/dnl/work/rasplayer-update.upload/payload/"
    ssh "${target}" \
        'rm -rf /home/dnl/work/rasplayer-update.old; if [ -e /home/dnl/work/rasplayer-update ]; then mv /home/dnl/work/rasplayer-update /home/dnl/work/rasplayer-update.old; fi; mv /home/dnl/work/rasplayer-update.upload /home/dnl/work/rasplayer-update; rasplayer-service deploy'
fi
