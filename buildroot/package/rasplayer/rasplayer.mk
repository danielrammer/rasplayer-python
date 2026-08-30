################################################################################
# RasPlayer application
################################################################################

RASPLAYER_VERSION = local
RASPLAYER_SITE = $(BR2_EXTERNAL_RASPLAYER_PATH)/..
RASPLAYER_SITE_METHOD = local
RASPLAYER_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = --exclude buildroot
RASPLAYER_DEPENDENCIES = python3 mpg123 alsa-lib alsa-utils python-rpi-gpio \
	python-vlc python-pyfluidsynth python-rasplayer-pygame openssl

define RASPLAYER_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) -Wall -Wextra -Werror \
		-o $(@D)/rasplayer-service \
		$(BR2_EXTERNAL_RASPLAYER_PATH)/package/rasplayer/rasplayer-service-control.c
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) -Wall -Wextra -Werror \
		-o $(@D)/rasplayer-deploy \
		$(BR2_EXTERNAL_RASPLAYER_PATH)/package/rasplayer/rasplayer-deploy.c \
		-lcrypto
endef

define RASPLAYER_PERMISSIONS
	/usr/bin/rasplayer-service f 4755 0 0 - - - - -
	/usr/sbin/rasplayer-deploy f 0755 0 0 - - - - -
	/home/dnl d 0755 0 0 - - - - -
	/home/dnl/RasPlayer d 0755 0 0 - - - - -
	/home/dnl/RasPlayer/Sounds r -1 1000 1000 - - - - -
	/home/dnl/work d 0755 1000 1000 - - - - -
	/opt/rasplayer r -1 0 0 - - - - -
endef

define RASPLAYER_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/home/dnl/RasPlayer/Sounds
	$(INSTALL) -d $(TARGET_DIR)/home/dnl/work
	$(INSTALL) -d $(TARGET_DIR)/opt/rasplayer/releases/image-base
	$(INSTALL) -m 0755 $(@D)/RasPlayer.py $(TARGET_DIR)/opt/rasplayer/releases/image-base/RasPlayer.py
	$(INSTALL) -m 0644 $(@D)/SoundPlayer.py $(@D)/SamplePlayer.py $(@D)/MusicPlayer.py \
		$(@D)/OnlinePlayer.py $(@D)/SynthPlayer.py $(@D)/command_path.py \
		$(@D)/systemd_notify.py $(TARGET_DIR)/opt/rasplayer/releases/image-base/
	ln -snf /home/dnl/RasPlayer/Sounds \
		$(TARGET_DIR)/opt/rasplayer/releases/image-base/Sounds
	ln -snf /opt/rasplayer/releases/image-base $(TARGET_DIR)/opt/rasplayer/current
	rm -f $(TARGET_DIR)/home/dnl/RasPlayer/RasPlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/SoundPlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/SamplePlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/MusicPlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/OnlinePlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/SynthPlayer.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/command_path.py \
		$(TARGET_DIR)/home/dnl/RasPlayer/systemd_notify.py
	test -d $(@D)/Sounds
	rsync -a --delete $(@D)/Sounds/ $(TARGET_DIR)/home/dnl/RasPlayer/Sounds/
	$(INSTALL) -d $(TARGET_DIR)/etc/init.d
	$(INSTALL) -m 0755 $(BR2_EXTERNAL_RASPLAYER_PATH)/board/rasplayer-pi3bplus/rootfs-overlay/etc/init.d/S50rasplayer $(TARGET_DIR)/etc/init.d/S50rasplayer
	$(INSTALL) -D -m 4755 $(@D)/rasplayer-service \
		$(TARGET_DIR)/usr/bin/rasplayer-service
	$(INSTALL) -D -m 0755 $(@D)/rasplayer-deploy \
		$(TARGET_DIR)/usr/sbin/rasplayer-deploy
	$(INSTALL) -d $(TARGET_DIR)/var/lib/rasplayer/deploy
endef

$(eval $(generic-package))
