#!/bin/sh
set -eu

chmod 0755 "${TARGET_DIR}/etc/init.d/rcS" \
    "${TARGET_DIR}/etc/init.d/S40provision" \
    "${TARGET_DIR}/etc/init.d/S41wifi" \
    "${TARGET_DIR}/etc/init.d/S50dropbear" \
    "${TARGET_DIR}/etc/init.d/S50rasplayer" \
    "${TARGET_DIR}/usr/bin/boottrace" \
    "${TARGET_DIR}/usr/bin/rasplayer-net-status" \
    "${TARGET_DIR}/usr/bin/rasplayer-udhcpc-script" \
    "${TARGET_DIR}/usr/sbin/boottrace-save" \
    "${TARGET_DIR}/usr/sbin/rasplayer-diagnostics-save"

# Do not let generated Ethernet DHCP/ifup scripts gate RasPlayer. The overlay
# provisioning and Wi-Fi worker are the only automatic network path.
rm -f "${TARGET_DIR}/etc/init.d/S40network" \
    "${TARGET_DIR}/etc/network/interfaces" \
    "${TARGET_DIR}/etc/network/if-pre-up.d/wait_iface"

# Keep application and network logs on the ext4 root filesystem.  /var/log is
# a volatile symlink to /tmp in this BusyBox image.
mkdir -p "${TARGET_DIR}/var/lib/rasplayer/logs"

# The application uses this distribution path for FluidSynth's soundfont.
if [ -f "${TARGET_DIR}/usr/share/soundfonts/FluidR3_GM.sf2" ]; then
    mkdir -p "${TARGET_DIR}/usr/share/sounds/sf2"
    ln -sf /usr/share/soundfonts/FluidR3_GM.sf2 \
        "${TARGET_DIR}/usr/share/sounds/sf2/FluidR3_GM.sf2"
fi
