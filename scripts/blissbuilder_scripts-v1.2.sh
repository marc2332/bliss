#------------------------------------------------------------------------
# The name of the package is  ${APPNAME}
# The name of the platform is  ${HOSTTYPE}
# The name of the parent directory of the package is ${PACKAGEROOT}
#
# Don't alter the __PRE_INST__, __POST_INST__, __PRE_UNIN__ and __POST_UNIN__
# keywords, they're used to create the rpm package.
#------------------------------------------------------------------------

################
# INSTALL
################

#__PRE_INST__
#------------------------------------------------------------------------
# This is called BEFORE the files being delivered,
PreInstall() {
# Forces to show executed commands.
set -x

echo " *********************** PreInstall() *********************** "

# for example to remove something like the .pth file ...
# /bin/rm -f ${PACKAGEROOT}/modules/${APPNAME}.pth

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
$GIT --version >/dev/null 2>&1 || { echo "ERROR: unusable git" ; return 0  ;}

# Clean destination directory.
cd /tmp/
rm -rf bliss.git/

# Clones git repo. (git: -> no key needed)
$GIT clone git://gitlab.esrf.fr/bliss/bliss.git  ./bliss.git

# why to do that ?
# -p : prepend to the existing content
# _CompOs_ : replaced by the good plateform by blissrc
blissrc -p BLISS_LIB_PATH '${BLISSADM}/python/bliss_modules/_CompOs_/'

}
#------------------------------------------------------------------------

#__POST_INST__
#------------------------------------------------------------------------
# This is called AFTER the files being delivered,
PostInstall() {
# Forces to show executed commands.
set -x
echo " *********************** PostInstall() *********************** "

# needed to find blissrc (and git?)
PATH=${PACKAGEROOT}/bin:${PATH}


# ESRF install.
cd /tmp/bliss.git/

# done in Makefile : cp setup.cfg.esrf setup.cfg

. blissrc

# for argparse...
PYTHONPATH=${PYTHONPATH}:/users/blissadm/python/bliss_modules:/users/blissadm/python/bliss_modules/${HOSTTYPE}

make install

}


###################
# UnInstall
###################


#------------------------------------------------------------------------
#__PRE_UNIN__
#------------------------------------------------------------------------
# This is called BEFORE the files being removed,
PreUnInstall() {
# Forces to show executed commands.
set -x

echo " *********************** PreUnInstall() *********************** "

# for example to save something ...
# cp ${PACKAGEROOT}/modules/${APPNAME}.pth ${PACKAGEROOT}/admin/old/

}


#------------------------------------------------------------------------
#__POST_UNIN__
#------------------------------------------------------------------------
# This is called AFTER the files being removed,
PostUnInstall() {
# Forces to show executed commands.
set -x

echo " *********************** PostUnInstall() *********************** "

# for example to update ...
# echo ${APPNAME} > ${PACKAGEROOT}/modules/${APPNAME}.pth

}
#------------------------------------------------------------------------
