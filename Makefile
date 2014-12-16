#
# E-Motion installation script.
#
# Creates links from standard blissadm directories to
# /users/blissadm/python/bliss_modules/bliss
#


EMOTION_PATH=/users/blissadm/python/bliss_modules/bliss
BLISSADM_PATH=/users/blissadm


DEV_EMOTION_PATH=/users/blissadm/dev/bliss

# Creates links
install:
	ln -sf ${EMOTION_PATH}/tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server
	ln -snf ${EMOTION_PATH} ${BLISSADM_PATH}/bliss
	mkdir -p /users/blissadm/local/userconf/bliss
	ln -sf ${EMOTION_PATH}/spec/tango_mot.mac ${BLISSADM_PATH}/spec/macros/tango_mot.mac

# "development installation"...
devi:
	ln -sf ${DEV_EMOTION_PATH}/tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server
	ln -sf ${DEV_EMOTION_PATH}/tango/BlissAxisManager.py ${BLISSADM_PATH}/server/src/BlissAxisManager.py
	ln -sf ${DEV_EMOTION_PATH}/tango/TgGevent.py ${BLISSADM_PATH}/server/src/TgGevent.py
	ln -sf ${DEV_EMOTION_PATH}/spec/tango_mot.mac ${BLISSADM_PATH}/spec/macros/tango_mot.mac


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

