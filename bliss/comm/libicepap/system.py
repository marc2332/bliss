"""IcePAP library"""

import sys

#-------------------------------------------------------------------------
# Library modules
#
import globals


#-------------------------------------------------------------------------
# Specific modules than must be in the PYTHONPATH
#
try:
    from ..libdeep import device  as deep_device
    from ..libdeep import log as deep_log
except ImportError:
    print 'ERROR: module "deep" not found'
    print 'HINT : add to your PYTHONPATH the location of this module'
    sys.exit(-1)




#-------------------------------------------------------------------------
# Class definition
#

class System():
    """Handle connection to an IcePAP device

    d = System("iceid241")
    d = System("iceid241", DEBUG1)

    d.command("IPMASK","255.255.255.0")
    print d.ackcommand("IPMASK","255.255.255.0")
    print d.command("?VER")

    print d.hostname()

    """

    def __init__(self, hostname, flags=""):
        """
        Get a connection to an IcePAP device identified with its hostname
        """

        # Save socket connections by keeping a non duplicated list
        # of DeepDevice objects. Therefore this class can not inherit
        # directly from DeepDevice one.
        if hostname not in globals._known_devices:
            # Mandatory libdeep argument for IcePAP devices
            argin_str   = ' '.join(["mode=icepap"]+[flags])
            deepdevice  = deep_device.DeepDevice(hostname, argin_str)

            # Save communication payload doing the hypothesis that all
            # axis of an IcePAP device have the same firmare version
            globals._known_commandlist[hostname] = deepdevice.getcommandlist()

            # Library global resource
            globals._known_devices[hostname] = deepdevice

        # Object initialization
        self._hostname   = hostname
        self._deepdevice = globals._known_devices[hostname]
        self._verbose    = deep_log.DBG_ERROR

    def close(self):
        """Close communication links"""
        if self._hostname in globals._known_devices:
            self._deepdevice.close()
            del globals._known_devices[self._hostname]

    def set_verbose(self, val):
        """Change the verbose level"""
        self._verbose = val
        self._deepdevice.set_verbose(val)

    def get_verbose(self):
        """Returns the current verbose level"""
        return self._verbose

    def hostname(self):
        """Returns the IcePAP system hostname"""
        return self._hostname 

    def command(self, str_cmd, in_data=None):
        """Send a command to the IcePAP system"""
        return self._deepdevice.command(str_cmd, in_data)

    def ackcommand(self, str_cmd, in_data=None):
        """Send a command with acknowledge to the IcePAP system"""
        return self._deepdevice.ackcommand(str_cmd, in_data)



