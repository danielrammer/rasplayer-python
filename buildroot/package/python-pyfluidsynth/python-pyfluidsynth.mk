PYTHON_PYFLUIDSYNTH_VERSION = 1.4.0
PYTHON_PYFLUIDSYNTH_SOURCE = pyfluidsynth-$(PYTHON_PYFLUIDSYNTH_VERSION).tar.gz
PYTHON_PYFLUIDSYNTH_SITE = https://files.pythonhosted.org/packages/a3/40/00985fe453bf85cfe1d586f236b97f84401e8ac203588e51840955ed835a
PYTHON_PYFLUIDSYNTH_SETUP_TYPE = setuptools
PYTHON_PYFLUIDSYNTH_DEPENDENCIES = python3 fluidsynth

# Normalize the legacy license string rejected by current setuptools.
define PYTHON_PYFLUIDSYNTH_FIX_METADATA
	if [ -f $(@D)/pyproject.toml ]; then \
		sed -i 's/^license = "MIT"/license = { text = "MIT" }/' $(@D)/pyproject.toml; \
	fi
endef
PYTHON_PYFLUIDSYNTH_POST_EXTRACT_HOOKS += PYTHON_PYFLUIDSYNTH_FIX_METADATA

$(eval $(python-package))
