#
# E-Motion installation script.
#
# Creates links from standard blissadm directories to
# /users/blissadm/python/bliss_modules/bliss
#


EMOTION_PATH=/users/blissadm/python/bliss_modules/bliss
BLISSADM_PATH=/users/blissadm

# Creates links
install:
	ln -sf ${EMOTION_PATH}/tango/bliss_server ${BLISSADM_PATH}/server/src/bliss_server
	ln -snf ${EMOTION_PATH} ${BLISSADM_PATH}/bliss
	ln -snf ${EMOTION_PATH}/tango/config ${BLISSADM_PATH}/local/userconf/bliss

# Builds sphinx documentation.
doc:
	cd doc/motors
	make html

# Removes links
clean:
	rm -rf *.pyc *~
	rm -f ${BLISSADM_PATH}/server/src/bliss_server
	rm -f ${BLISSADM_PATH}/bliss
	rm -f ${BLISSADM_PATH}/local/userconf/bliss


