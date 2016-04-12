#
# E-Motion installation at ESRF.
#

# Installation directories :
# /users/blissadm/python/bliss_modules/
# /users/blissadm/local/userconf/bliss/
# /users/blissadm/server/src/BlissAxisManager


BLISSADM_PATH=/users/blissadm
BLISS_ENV_VAR=${BLISSADM_PATH}/local/BLISS_ENV_VAR
CONFIG_PATH=${BLISSADM_PATH}/local/beamline_configuration

DEV_PATH=${PWD}

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

# "Distribution" installation.
# Copy of files from current git directory.
install:

        ####  ESRF install only...
	cp -f setup.cfg.esrf setup.cfg

        ####  install of the py module.
        # this install:
        #   * in ~/local/bin/ : beacon-server  beacon-server-list  bliss  bliss_webserver
	python setup.py install

	rm setup.cfg

        # Install beacon daemon blcontrol startup script
	@echo ""
	@echo "Adding beacon daemon to BLControl start-up/shudown structure..."
	mkdir -p ${BLISSADM_PATH}/admin/etc
	cp -f scripts/admin/S10beacon ${BLISSADM_PATH}/admin/etc

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
	mkdir -p ${BLISSADM_PATH}/server/src
	find tango -type f -perm ${PERM_EXE} -exec cp --backup=simple --suffix=.bup {} ${BLISSADM_PATH}/server/src/ \;


        ####  Copy SPEC macros, only if spec/macros/ directory exists.
	@echo ""
ifneq ($(wildcard ${BLISSADM_PATH}/spec/macros/),)
	@echo "\"spec/macros/\" directory exists; Copying SPEC macros..."
	find spec -name \*.mac -exec cp -v --backup=simple --suffix=.bup {} ${BLISSADM_PATH}/spec/macros \;
else
	@echo "\"spec/macros/\" directory does not exist"
endif


# Builds sphinx documentation.
doc:
	cd doc/motors
	make html

clean:
	rm -rf ${BLISSADM_PATH}/python/bliss_modules/bliss/
	rm -f ${BLISSADM_PATH}/server/src/CT2
	rm -f ${BLISSADM_PATH}/server/src/BlissAxisManager
	rm -f ${BLISSADM_PATH}/server/src/Nanodac
	rm -f ${BLISSADM_PATH}/server/src/Gpib
	rm -f ${BLISSADM_PATH}/server/src/Musst

