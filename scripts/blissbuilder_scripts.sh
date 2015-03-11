#------------------------------------------------------------------------
# The name of the package is  ${APPNAME}
# The name of the platform is  ${HOSTTYPE}
# The name of the parent directory of the package is ${PACKAGEROOT}
#
# Don't alter the __PRE_INST__, __POST_INST__, __PRE_UNIN__ and __POST_UNIN__
# keywords, they're used to create the rpm package.
#------------------------------------------------------------------------


#__PRE_INST__
#------------------------------------------------------------------------
# This is called BEFORE the files being delivered,
PreInstall() {

# for example to remove something like the .pth file ...
# /bin/rm -f ${PACKAGEROOT}/modules/${APPNAME}.pth
#set -x

    # needed to find blissrc (and git?)
    PATH=${PACKAGEROOT}/bin:${PATH}

    echo `type git`
    GIT=`type git > /dev/null 2>&1 || echo "notfound"`

    # "-n" : test if string is non-null.
    if [ -n "${GIT}" ]; then
        GIT=${PACKAGEROOT}/bin/git
        echo "search git as :  $GIT"
        if [ ! -x "${GIT}" ]; then
            echo "WARNING: no git installed"
            return 0
        fi
    else
        GIT=`which git`
        echo "git found : $GIT"
    fi

    # check that the git found is usable
    $GIT --version >/dev/null 2>&1 || { echo "WARNING: unusable git" ; return 0  ;}

    cd /tmp
    rm -rf /tmp/bliss/

    echo "unset http_proxy to allow http cloning"
    unset http_proxy
    $GIT clone http://gitlab.esrf.fr/bliss/bliss.git

    # $GIT clone git@gitlab.esrf.fr:bliss/bliss.git

    cd bliss

    #  "a new hope" tag
    # $GIT checkout 1.5

    echo "get Python Strikes Back 1.6 tag"
    $GIT checkout 1.6

    # will install in /users/blissadm/python/bliss_modules/bliss/
    # python setup.py install
    echo "make install..."
    make install

}

#------------------------------------------------------------------------

#__POST_INST__
#------------------------------------------------------------------------
# This is called AFTER the files being delivered,
PostInstall() {



########
####  Everything is now done in Makefile.
########


# for example to create the .pth file ...
# echo ${APPNAME} > ${PACKAGEROOT}/modules/${APPNAME}.pth
#set -x

echo "postinstall"

# EMOTIONHOME=${PACKAGEROOT}/python/bliss_modules/${APPNAME}
# if [ -e ${EMOTIONHOME} ]; then

#   # install config files templates
#   CONFIG_TEMPLATE_DIR=${PACKAGEROOT}/local/userconf/bliss
#   cp /tmp/bliss/config/*.xml ${CONFIG_TEMPLATE_DIR}
#   cp /tmp/bliss/config/*.yml ${CONFIG_TEMPLATE_DIR}
# 
#   # install doc
# #  DOC_DIR=${PACKAGEROOT}/doc/bliss
#  # if [ -e ${CONFIG_TEMPLATE_DIR} ]; then
#   #  echo "Installing doc"
#    # cp 
#     #fi
# 
#   # install usage demos
#   DEMO_DIR=${EMOTIONHOME}/demos/
#   if [ -e ${DEMO_DIR} ]; then
#       echo "Installing demos"
#       cp /tmp/bliss/tests/simple_usage.py ${DEMO_DIR}/
#   fi
# 
#   # install macros only if spec/macros/ dir exists.
#   if [ -e ${PACKAGEROOT}/spec/macros ]; then
#     cp /tmp/bliss/spec/tango_mot.mac  /users/blissadm/spec/macros/
#   fi
# 
#   #install TANGO DS
#   echo "Install tango DS and startup script"
#   cp  /tmp/bliss/tango/bliss_server  /users/blissadm/server/src/
#   cp  /tmp/bliss/tango/Bliss.py    /users/blissadm/server/src/
# fi


}
#------------------------------------------------------------------------

#__PRE_UNIN__
#------------------------------------------------------------------------
# This is called BEFORE the files being removed, 
PreUnInstall() {

# for example to save something ...
# cp ${PACKAGEROOT}/modules/${APPNAME}.pth ${PACKAGEROOT}/admin/old/
set -x

}
#------------------------------------------------------------------------

#__POST_UNIN__
#------------------------------------------------------------------------
# This is called AFTER the files being removed, 
PostUnInstall() {

# for example to update ...
# echo ${APPNAME} > ${PACKAGEROOT}/modules/${APPNAME}.pth
#set -x

EMOTIONHOME=${PACKAGEROOT}/python/bliss_modules/${APPNAME}

if [ -e ${EMOTIONHOME} ]; then
    echo "Removing EMotion lib : ${EMOTIONHOME}"
    rm -rf ${EMOTIONHOME}
fi

# remove config files templates
CONFIG_TEMPLATE_DIR=${PACKAGEROOT}/local/userconf/bliss
if [ -e ${CONFIG_TEMPLATE_DIR} ]; then
    echo "Removing templates : ${CONFIG_TEMPLATE_DIR}"
    rm ${CONFIG_TEMPLATE_DIR}/*.xml
    rm ${CONFIG_TEMPLATE_DIR}/*.yml
fi

# remove doc
#  DOC_DIR=${PACKAGEROOT}/doc/bliss
# if [ -e ${DOC_DIR} ]; then
#  echo "Removing doc : ${DOC_DIR}"
# rm
#fi

# remove usage demos
DEMO_DIR=${EMOTIONHOME}/demos/
if [ -e ${DEMO_DIR} ]; then
    echo "Removing demos : ${DEMO_DIR}"
    rm -f  ${DEMO_DIR}/simple_usage.py
    rmdir ${DEMO_DIR}/
fi

# removes macros
echo "Removing macro /users/blissadm/spec/macros/tango_mot.mac"
rm -f  /users/blissadm/spec/macros/tango_mot.mac

# removes TANGO DS
echo "Removing tango ds and startup script /users/blissadm/server/src/bliss_server, Bliss.py"
rm -f /users/blissadm/server/src/bliss_server
rm -f /users/blissadm/server/src/Bliss.py
}
#------------------------------------------------------------------------
