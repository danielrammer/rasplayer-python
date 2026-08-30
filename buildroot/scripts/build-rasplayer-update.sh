#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 RELEASE_ID RASPLAYER_SERVICE_BINARY OUTPUT_DIR" >&2
    exit 2
fi

release=$1
helper=$2
output=$3
case "${release}" in
    ''|.*|*[!A-Za-z0-9._-]*) echo "Invalid release id: ${release}" >&2; exit 2 ;;
esac
[ -f "${helper}" ] || { echo "Missing helper binary: ${helper}" >&2; exit 1; }
[ ! -e "${output}" ] || { echo "Refusing to overwrite ${output}" >&2; exit 1; }

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "${script_dir}/../.." && pwd)
private_key=${repo}/.local/rasplayer-signing/rasplayer-release-private.pem
sh "${script_dir}/create-update-signing-key.sh" >/dev/null
[ -f "${private_key}" ] || { echo "Missing private key: ${private_key}" >&2; exit 1; }
parent=$(dirname -- "${output}")
mkdir -p "${parent}"
temporary=$(mktemp -d "${parent}/.rasplayer-update.XXXXXX")
cleanup() { rm -rf "${temporary}"; }
trap cleanup EXIT INT TERM
mkdir -p "${temporary}/bundle/payload"

files='RasPlayer.py SoundPlayer.py SamplePlayer.py MusicPlayer.py OnlinePlayer.py SynthPlayer.py command_path.py systemd_notify.py'
for file in ${files}; do
    cp "${repo}/${file}" "${temporary}/bundle/payload/${file}"
done
cp "${helper}" "${temporary}/bundle/payload/rasplayer-service"

manifest=${temporary}/bundle/manifest
{
    echo 'format=rasplayer-update-v1'
    echo "release=${release}"
    for file in ${files}; do
        hash=$(sha256sum "${temporary}/bundle/payload/${file}" | awk '{print $1}')
        echo "${file}=${hash}"
    done
    hash=$(sha256sum "${temporary}/bundle/payload/rasplayer-service" | awk '{print $1}')
    echo "rasplayer-service=${hash}"
} >"${manifest}"
openssl pkeyutl -sign -rawin -inkey "${private_key}" \
    -in "${manifest}" -out "${temporary}/bundle/signature"
chmod -R u=rwX,go=rX "${temporary}/bundle"
mv "${temporary}/bundle" "${output}"
echo "Created signed RasPlayer update: ${output}"
