#
# bliss installation.
#

# Installation directories for ESRF:
# /users/blissadm/python/bliss_modules/
# /users/blissadm/local/userconf/bliss/
# /users/blissadm/server/src/BlissAxisManager

BLISS_ESRF ?= $(shell if id blissadm >/dev/null 2>&1; then echo "1"; else echo "0"; fi)
EUID = $(shell id -u)

# ESRF specific configuration
ifeq ($(BLISS_ESRF),1)
  BLISSADM ?= /users/blissadm
  BLISS_ENV_VAR ?= ${BLISSADM}/local/BLISS_ENV_VAR
  CONFIG_PATH ?= ${BLISSADM}/local/beamline_configuration
endif

DEV_PATH=${PWD}
MAKEFILE_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

FIND_VER=$(shell for t in $$(find --version); do \
                   echo "$$t" | grep -E "[0-9]+(\.[0-9]+){2}" && break; done)
FIND_MAJ=$(shell echo "${FIND_VER}" | cut -d. -f1)
FIND_MIN=$(shell echo "${FIND_VER}" | cut -d. -f2)
OLD_FIND=$(shell test ${FIND_MAJ} -eq 4 -a ${FIND_MIN} -lt 2 && echo 1)
ifeq (${OLD_FIND},1)
PERM_EXE="+a+x"
else
PERM_EXE="/a+x"
endif

.PHONY: bootstrap install clean doc 

# "Distribution" installation.
# Copy of files from current git directory.
bootstrap:
	${MAKEFILE_DIR}/bootstrap $(BLISS_ESRF) 
	$(MAKE) install

install:
ifneq ($(BLISS_ESRF),0)
ifeq ($(EUID), 0)
	#xauth merge /users/blissadm/.Xauthority
	su blissadm -c "$(MAKE) install"
else
	cp -f setup.cfg.esrf setup.cfg

        ####  install of the py module.
        # this install:
        #   * in ~/local/bin/ : beacon-server  beacon-server-list  bliss  bliss_webserver
	python setup.py install

ifneq ($(BLISS_ESRF),0)
	rm setup.cfg

        # Install beacon daemon blcontrol startup script
	@echo ""
	@echo "Adding beacon daemon to BLControl start-up/shudown structure..."
	mkdir -p ${BLISSADM}/admin/etc
	cp -f scripts/admin/S10beacon ${BLISSADM}/admin/etc

        # Add default beacon-server parameters to BLISS_ENV_VAR
	@echo ""
	@echo "Checking beacon server start-up config..."
	grep -q BEACON_DB_PATH ${BLISS_ENV_VAR} || \
		echo 'BEACON_DB_PATH='${CONFIG_PATH}' export BEACON_DB_PATH' \
			>> ${BLISS_ENV_VAR}

	grep -q BEACON_PORT ${BLISS_ENV_VAR} || \
		echo 'BEACON_PORT=25000 export BEACON_PORT' >> ${BLISS_ENV_VAR}

	grep -q BEACON_WEB_PORT ${BLISS_ENV_VAR} || \
		echo 'BEACON_WEB_PORT=9030 export BEACON_WEB_PORT' >> ${BLISS_ENV_VAR}

        # Creates config directory.
	mkdir -p ${CONFIG_PATH}; chmod 777 ${CONFIG_PATH}

        ####  Copy Tango servers.
	@echo ""
	@echo "Copying Tango DS start-up scripts..."
	mkdir -p ${BLISSADM}/server/src
	find tango -type f -perm ${PERM_EXE} -exec cp --backup=simple --suffix=.bup {} ${BLISSADM}/server/src/ \;


        ####  Copy SPEC macros, only if spec/macros/ directory exists.
	@echo ""
ifneq ($(wildcard ${BLISSADM}/spec/macros/),)
	@echo "\"spec/macros/\" directory exists; Copying SPEC macros..."
	find spec -name \*.mac -exec cp -v --backup=simple --suffix=.bup {} ${BLISSADM}/spec/macros \;
else
	@echo "\"spec/macros/\" directory does not exist"
endif
endif
endif
endif

# Builds sphinx documentation.
doc:
	cd doc/motors
	make html

clean:
ifneq ($(BLISS_ESRF),0)
	rm -rf ${BLISSADM}/python/bliss_modules/bliss/
	find tango -type f -perm ${PERM_EXE} -exec bash -c 'rm -f ${BLISSADM}/server/src/`basename {}`' \;
endif


tests_axis_ds:
        # needs ~/server/src/BlissAxisManager batest to be running
	python tests/motors/TestBlissAxisManagerDS.py
	python tests/motors/TestSetpoint.py


tests_axis:
	python tests/motors/TestCustomCommands.py
	python tests/motors/TestCustomAttributes.py
	python tests/motors/TestEncoder.py
	python tests/motors/TestEncoderBeacon.py
	python tests/motors/TestGroup.py
	python tests/motors/TestLogging.py
	python tests/motors/TestMockupController.py
	python tests/motors/TestSimplestCalcController.py
	python tests/motors/TestStates.py
	python tests/motors/TestTgGevent.py
	python tests/motors/TestSettings.py

#	python tests/motors/TestBeaconMockupController.py   config file to be adapted in yml...
#	python tests/motors/TestBeaconSlits.py              config file to be adapted in yml...
#	python tests/motors/TestSlits.py
#       python tests/motors/TestTcpComm.py                  does not finish ?


