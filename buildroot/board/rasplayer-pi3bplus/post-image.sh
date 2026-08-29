#!/bin/sh
set -eu

BOARD_DIR="${BR2_EXTERNAL_RASPLAYER_PATH}/board/rasplayer-pi3bplus"
GENIMAGE_CFG="${BOARD_DIR}/genimage.cfg"
GENIMAGE_TMP="${BUILD_DIR}/genimage.tmp"
rm -rf "${GENIMAGE_TMP}"
mkdir -p "${GENIMAGE_TMP}"
genimage --rootpath "${TARGET_DIR}" \
  --tmppath "${GENIMAGE_TMP}" \
  --inputpath "${BINARIES_DIR}" \
  --outputpath "${BINARIES_DIR}" \
  --config "${GENIMAGE_CFG}"
