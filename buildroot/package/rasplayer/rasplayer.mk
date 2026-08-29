################################################################################
# RasPlayer application
################################################################################

RASPLAYER_VERSION = local
RASPLAYER_SITE = $(BR2_EXTERNAL_RASPLAYER_PATH)/..
RASPLAYER_SITE_METHOD = local
RASPLAYER_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = --exclude buildroot
RASPLAYER_DEPENDENCIES = python3 mpg123 alsa-lib alsa-utils python-rpi-gpio \
	python-vlc python-pyfluidsynth python-rasplayer-pygame

define RASPLAYER_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/home/dnl/RasPlayer
	$(INSTALL) -m 0755 $(@D)/RasPlayer.py $(TARGET_DIR)/home/dnl/RasPlayer/RasPlayer.py
	$(INSTALL) -m 0644 $(@D)/SoundPlayer.py $(@D)/SamplePlayer.py $(@D)/MusicPlayer.py \
		$(@D)/OnlinePlayer.py $(@D)/SynthPlayer.py $(@D)/command_path.py \
		$(@D)/systemd_notify.py $(TARGET_DIR)/home/dnl/RasPlayer/
	test -d $(@D)/Sounds
	$(INSTALL) -d $(TARGET_DIR)/home/dnl/RasPlayer/Sounds
	rsync -a --delete $(@D)/Sounds/ $(TARGET_DIR)/home/dnl/RasPlayer/Sounds/
	$(INSTALL) -d $(TARGET_DIR)/etc/init.d
	$(INSTALL) -m 0755 $(BR2_EXTERNAL_RASPLAYER_PATH)/board/rasplayer-pi3bplus/rootfs-overlay/etc/init.d/S50rasplayer $(TARGET_DIR)/etc/init.d/S50rasplayer
endef

$(eval $(generic-package))
