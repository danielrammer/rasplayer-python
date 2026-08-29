include $(sort $(wildcard $(BR2_EXTERNAL_RASPLAYER_PATH)/package/*/*.mk))

# RasPlayer loads its short UI samples through pygame.mixer.Sound(), and all
# deployed samples are MP3. Buildroot 2024.02 disables SDL2_mixer's MP3 codec
# unconditionally, so override that default and use SDL2_mixer's bundled
# dr_mp3 decoder without adding another runtime service or startup dependency.
SDL2_MIXER_CONF_OPTS := $(filter-out --disable-music-mp3,$(SDL2_MIXER_CONF_OPTS))
SDL2_MIXER_CONF_OPTS += --enable-music-mp3 --enable-music-mp3-drmp3
