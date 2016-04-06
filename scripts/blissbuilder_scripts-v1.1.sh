#------------------------------------------------------------------------
# template of installation scripts
# 2002-ESRF, BLISS group
# $Log: rpmscripts.script,v $
# Revision 1.37  2003/09/30 07:02:46  claustre
# pass output-meta parameter to scripts, see RPM book page 184 for details.
#
# Revision 1.36  2002/12/09 15:42:27  claustre
# Revision number sorting bug corrected + few others.
#
# Revision 1.35  2002/10/30 16:51:41  claustre
# Enable/Disable project feature added
#
# Revision 1.34  2002/10/24 14:26:30  claustre
# bugs fixed, modified confirm-box of project removal-action
#
# Revision 1.33  2002/10/18 12:18:17  claustre
# bug fixed, minor version number and dependency management
#
# Revision 1.32  2002/10/17 09:23:13  claustre
# improve 'All' mode for platform file sharing + new Depend Page listview
#
# Revision 1.31  2002/10/10 15:22:09  claustre
# Improve version duplication and dependency settings
#
# Revision 1.3  2002/10/08 11:19:16  claustre
# New package naming convention, e.g. SPEC-suse64-1.0-1.src.rpm
#
# Revision 1.2  2002/09/12 16:01:51  claustre
# last version with rpm platforms next one will only manage src packages.
#
# Revision 1.1  2002/08/22 07:31:10  claustre
# Optimized version
#
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
set -x

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
rm -rf bliss
$GIT clone git://gitlab.esrf.fr/bliss/bliss.git  ./bliss.git
cd bliss.git
# $GIT reset --hard cdfc4a45e8d94be6b776c82c7829d126b4e4c218
cp setup.cfg.esrf setup.cfg

}
#------------------------------------------------------------------------

#__POST_INST__
#------------------------------------------------------------------------
# This is called AFTER the files being delivered, 
PostInstall() {

# for example to create the .pth file ...
# echo ${APPNAME} > ${PACKAGEROOT}/modules/${APPNAME}.pth
set -x

PATH=${PACKAGEROOT}/bin:${PATH}

cd /tmp/bliss.git
python setup.py install

blissrc -p BLISS_LIB_PATH '${BLISSADM}/python/bliss_modules/_CompOs_/'

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
set -x

}
#------------------------------------------------------------------------
