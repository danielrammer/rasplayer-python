#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
    echo "Usage: $0" >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "${script_dir}/../.." && pwd)
private_dir=${repo}/.local/rasplayer-signing
private_key=${private_dir}/rasplayer-release-private.pem
public_key=${repo}/buildroot/rasplayer-update-public.pem

mkdir -p "${private_dir}"
chmod 0700 "${private_dir}"
umask 077

if [ ! -e "${private_key}" ]; then
    if [ -e "${public_key}" ]; then
        echo "Public key exists but private key is missing; refusing to create a mismatched pair" >&2
        exit 1
    fi
    openssl genpkey -algorithm ED25519 -out "${private_key}"
    echo "Generated deployment signing key"
elif [ ! -f "${private_key}" ]; then
    echo "Private-key path is not a regular file: ${private_key}" >&2
    exit 1
fi
chmod 0600 "${private_key}"
openssl pkey -in "${private_key}" -noout >/dev/null

derived_public=$(mktemp "${private_dir}/.rasplayer-public.XXXXXX")
cleanup() { rm -f "${derived_public}"; }
trap cleanup EXIT INT TERM
openssl pkey -in "${private_key}" -pubout -out "${derived_public}"

if [ -e "${public_key}" ]; then
    [ -f "${public_key}" ] || { echo "Public-key path is not a regular file: ${public_key}" >&2; exit 1; }
    openssl pkey -pubin -in "${public_key}" -noout >/dev/null
    if ! cmp -s "${derived_public}" "${public_key}"; then
        echo "Public key does not correspond to the local private key: ${public_key}" >&2
        exit 1
    fi
else
    chmod 0644 "${derived_public}"
    mv "${derived_public}" "${public_key}"
    derived_public=${private_dir}/.rasplayer-public.removed
    echo "Exported deployment public key"
fi
chmod 0644 "${public_key}"

fingerprint=$(openssl pkey -pubin -in "${public_key}" -outform DER | sha256sum | awk '{print $1}')
echo "Private key: ${private_key}"
echo "Public key:  ${public_key}"
echo "Pair verified; public-key SHA-256: ${fingerprint}"
