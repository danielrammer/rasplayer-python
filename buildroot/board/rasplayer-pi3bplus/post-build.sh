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
    "${TARGET_DIR}/usr/sbin/rasplayer-diagnostics-save" \
    "${TARGET_DIR}/usr/sbin/rasplayer-deploy"
chmod 4755 "${TARGET_DIR}/usr/bin/rasplayer-service"

# Do not let generated Ethernet DHCP/ifup scripts gate RasPlayer. The overlay
# provisioning and Wi-Fi worker are the only automatic network path.
rm -f "${TARGET_DIR}/etc/init.d/S40network" \
    "${TARGET_DIR}/etc/network/interfaces" \
    "${TARGET_DIR}/etc/network/if-pre-up.d/wait_iface"

# Keep application and network logs on the ext4 root filesystem.  /var/log is
# a volatile symlink to /tmp in this BusyBox image.
mkdir -p "${TARGET_DIR}/var/lib/rasplayer/logs"

# Buildroot's Dropbear package installs /etc/dropbear as a dangling link to
# /var/run/dropbear for read-only-rootfs targets. This image has a writable
# ext4 root and needs a persistent, device-unique host key across reboots.
if [ -L "${TARGET_DIR}/etc/dropbear" ]; then
    dropbear_link=$(readlink "${TARGET_DIR}/etc/dropbear")
    if [ "${dropbear_link}" != "/var/run/dropbear" ]; then
        echo "Unexpected /etc/dropbear symlink: ${dropbear_link}" >&2
        exit 1
    fi
    rm -f "${TARGET_DIR}/etc/dropbear"
fi
mkdir -p "${TARGET_DIR}/etc/dropbear"
chmod 0700 "${TARGET_DIR}/etc/dropbear"

# The application uses this distribution path for FluidSynth's soundfont.
if [ -f "${TARGET_DIR}/usr/share/soundfonts/FluidR3_GM.sf2" ]; then
    mkdir -p "${TARGET_DIR}/usr/share/sounds/sf2"
    ln -sf /usr/share/soundfonts/FluidR3_GM.sf2 \
        "${TARGET_DIR}/usr/share/sounds/sf2/FluidR3_GM.sf2"
fi
