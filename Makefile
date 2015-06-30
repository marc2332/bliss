#
# E-Motion installation at ESRF.
#

# Installation directories :
# /users/blissadm/python/bliss_modules/
# /users/blissadm/local/userconf/bliss/
# /users/blissadm/server/src/bliss_server


BLISSADM_PATH=/users/blissadm

MOD_PATH=${BLISSADM_PATH}/python/bliss_modules

CONFIG_PATH=${BLISSADM_PATH}/local/userconf/bliss


DEV_PATH=${PWD}

# "Distribution" installation.
# Copy of files from current git directory.
install:

        ####  ESRF install only...
	cp -f setup.cfg.esrf setup.cfg

        ####  install of the py module.
	python setup.py install

	rm setup.cfg

        ####  config dir
	mkdir -p ${CONFIG_PATH}; chmod 777 ${CONFIG_PATH}

        ####  tango server and startup-script
	mkdir -p ${BLISSADM_PATH}/server/src
	cp --backup=simple --suffix=.bup tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server

	cp --backup=simple --suffix=.bup tango/BlissAxisManager.py ${BLISSADM_PATH}/server/src/BlissAxisManager.py

	cp --backup=simple --suffix=.bup tango/TgGevent.py ${BLISSADM_PATH}/server/src/TgGevent.py

        ####  Spec macros
	cp --backup=simple --suffix=.bup spec/tango_mot.mac ${BLISSADM_PATH}/spec/macros/tango_mot.mac


# Builds sphinx documentation.
doc:
	cd doc/motors
	make html


