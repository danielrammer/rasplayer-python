PYTHON_VLC_VERSION = 3.0.21203
PYTHON_VLC_SOURCE = python_vlc-$(PYTHON_VLC_VERSION).tar.gz
PYTHON_VLC_SITE = https://files.pythonhosted.org/packages/4b/5b/f9ce6f0c9877b6fe5eafbade55e0dcb6b2b30f1c2c95837aef40e390d63b
PYTHON_VLC_SETUP_TYPE = setuptools
PYTHON_VLC_DEPENDENCIES = python3 vlc

$(eval $(python-package))
