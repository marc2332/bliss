#
# E-Motion installation at ESRF.
#

# Installation directories :
# /users/blissadm/python/bliss_modules/
# /users/blissadm/local/userconf/bliss/
# /users/blissadm/server/src/BlissAxisManager


BLISSADM_PATH=/users/blissadm

CONFIG_PATH=${BLISSADM_PATH}/local/beamline_configuration/

MYHOSTNAME=$(shell hostname)

DEV_PATH=${PWD}

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

        ###### To do only on a NETHOST :
ifeq ($(MYHOSTNAME),$(NETHOST))
	@echo "I am on a NETHOST, "$(MYHOSTNAME)
        # Makes a link to be beacon-server dserver startable.
	mkdir -p ${BLISSADM_PATH}/server/src
	ln -sf ${BLISSADM_PATH}/local/bin/beacon-server ${BLISSADM_PATH}/server/src/beacon-server
        # Creates config directory.
	mkdir -p ${CONFIG_PATH}; chmod 777 ${CONFIG_PATH}
else
	@echo "I am not on a NETHOST"
endif


        ####  Copy Tango servers.
        # -perm /a+x : does not work on redhate4...
        # find tango/ -type f -perm /a+x -exec cp --backup=simple --suffix=.bup {} ${BLISSADM_PATH}/server/src/ \;
	cp --backup=simple --suffix=.bup tango/CT2 ${BLISSADM_PATH}/server/src/
	cp --backup=simple --suffix=.bup tango/BlissAxisManager ${BLISSADM_PATH}/server/src/
	cp --backup=simple --suffix=.bup tango/Nanodac ${BLISSADM_PATH}/server/src/
	cp --backup=simple --suffix=.bup tango/Gpib ${BLISSADM_PATH}/server/src/
	cp --backup=simple --suffix=.bup tango/Musst ${BLISSADM_PATH}/server/src/


        ####  Copy SPEC macros, only if spec/macros/ directory exists.
ifneq ($(wildcard ${BLISSADM_PATH}/spec/macros/),)
	@echo "\"spec/macros/\" directory exists"
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

