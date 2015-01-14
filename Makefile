#
# E-Motion installation script.
#
# Creates links from standard blissadm directories to
# /users/blissadm/python/bliss_modules/bliss
#

BLISSADM_PATH=/users/blissadm

MOD_PATH=${BLISSADM_PATH}/python/bliss_modules

CONFIG_PATH=${BLISSADM_PATH}/local/userconf/bliss


DEV_PATH=${PWD}

# "Distribution" installation.
# Copy of files from current git directory.
install:
        # install of the py module.
	python setup.py install

        # config dir and template files.
	mkdir -p ${CONFIG_PATH}; chmod 777 ${CONFIG_PATH}

        # tango server and startup-script
	cp --backup=simple --suffix=.bup tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server

	cp --backup=simple --suffix=.bup tango/BlissAxisManager.py ${BLISSADM_PATH}/server/src/BlissAxisManager.py

	cp --backup=simple --suffix=.bup tango/TgGevent.py ${BLISSADM_PATH}/server/src/TgGevent.py

        # Spec macros
	cp --backup=simple --suffix=.bup spec/tango_mot.mac ${BLISSADM_PATH}/spec/macros/tango_mot.mac


# "Development" installation.
# Creates links from current git directory.
devi: install

        # remove install...

        # Links do dev version
	ln -s ${DEV_PATH}/bliss ${MOD_PATH}/bliss

        # tango
	ln -sf ${DEV_PATH}/tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server
	ln -sf ${DEV_PATH}/tango/BlissAxisManager.py ${BLISSADM_PATH}/server/src/BlissAxisManager.py
	ln -sf ${DEV_PATH}/tango/TgGevent.py ${BLISSADM_PATH}/server/src/TgGevent.py

        # Spec
	ln -sf ${DEV_PATH}/spec/tango_mot.mac ${BLISSADM_PATH}/spec/macros/tango_mot.mac


# ACHTUNG
remove:
	rm -rf ${MOD_PATH}/bliss_orig


# Builds sphinx documentation.
doc:
	cd doc/motors
	make html


# Removes links
clean:
	rm -rf *.pyc *~
	rm -f ${BLISSADM_PATH}/server/src/bliss_server
	rm -f ${BLISSADM_PATH}/bliss
	rm -f ${BLISSADM_PATH}/spec/macros/tango_mot.mac

