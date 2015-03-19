"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import string


#-------------------------------------------------------------------------
# Library modules
#
import globals


#-------------------------------------------------------------------------
# Constant defintions
#
AXISNAME_FROM_DSP  = "__use_dsp_name"
AXISNAME_AUTO      = "__use_automatic_naming"

EXCLUSIVE          = "mode=exclusive"
READONLY           = "mode=readonly"
DONTMOVE           = "mode=dontmove"


#-------------------------------------------------------------------------
# Inteface function
#
def axis_to_name(axis):
    try:
        return axis.name()
    except:
        raise ValueError("invalid axis object")


def name_to_axis(name):
    try:
        return globals._known_axis[name]
    except:
        raise ValueError("invalid axis name \"%s\""%name)


def addr_to_axis(argin, addr):
    """Returns the axis object corresponding the system:addr given
    The IcePAP system can be specified with its hostname or an object
    """

    # The system could be specified as an object or a hostname string
    if isinstance(argin, basestring):
        return hostname_to_axis(argin, addr)
    else:
        return system_to_axis(argin, addr)


def hostname_to_axis(hostname, addr):
    # Look for a matching axis in the global library resource
    try:
        for name in globals._known_axis:
            axis = name_to_axis(name)
            if axis.system().hostname() == hostname:
                if axis.address() == addr:
                    return axis
    except:
        raise ValueError("invalid axis address")

    # Abnormal end
    raise ValueError("axis not found")


def system_to_axis(system, addr):
    # Look for a matching axis in the global library resource
    try:
        for name in globals._known_axis:
            axis = name_to_axis(name)
            if axis.system() == system:
                if axis.address() == addr:
                    return axis
    except:
        raise ValueError("invalid axis address")

    # Abnormal end
    raise ValueError("axis not found")



#-------------------------------------------------------------------------
# Inteface function
#
def status_ismoving(stat):
    """Returns True if the axis status given indicates a motion"""

    # From IcePAP documentation:
    #   -the MOVING   (10) goes down at the end of the trajectory
    #   -the SETTLING (11) goes down at the end of close loop algorythm
    if (stat & (1<<10)) or (stat & (1<<11)):
        return True

    # During a HOMING sequence, several motions take place,
    # therefore the MOVING/SETTLING pair can be unset. But the READY remains
    # unset during all the HOMING sequence. To distinguish a non READY axis
    # due to error condition from moving condition, the POWER bit
    # must also be checked
    #   -the READY    (09) goes down on error or moving
    #   -the POWERON  (23) goes down on error
    if (not (stat & (1<<9))) and (stat & (1<<23)):
        return True

    # Any motion in progress
    return False

def status_set_ismoving(stat, val=True):
    return status_set_bit(stat, 10, val)

def status_set_isready(stat, val=True):
    return status_set_bit(stat,  9, val)

def status_set_bit(stat, bit, val):
    if val:
        return (stat |  (1<<bit)) & ((1<<32)-1)
    else:
        return (stat & ~(1<<bit)) & ((1<<32)-1)

def status_isready(stat):
    """
    Returns True if the axis status given indicates 
    that the axis is ready to move
    """

    return ((stat & (1<<9)) != 0)


def status_lowlim(stat):
    """
    Returns True if the axis status given indicates 
    a low limitswitch active
    """

    return ((stat & (1<<19)) != 0)


def status_highlim(stat):
    """
    Returns True if the axis status given indicates
    a high limitswitch active
    """

    return ((stat & (1<<18)) != 0)


def status_home(stat):
    """
    Returns True if the axis status given indicates
    a HOME switch active
    """

    return ((stat & (1<<20)) != 0)



#-------------------------------------------------------------------------
# Inteface function
#
def axis_status(axis):
    try:
        return axis.status()
    except:
        raise ValueError("invalid axis object")


def axis_pos(axis):
    try:
        return axis.pos()
    except:
        raise ValueError("invalid axis object")


def axis_move(axis, tarposition):
    try:
        return axis.move(tarposition)
    except:
        raise ValueError("invalid axis object")



def axis_command(axis, str_cmd, in_data=None):
    try:
        return axis.command(str_cmd, in_data)
    except:
        raise ValueError("invalid axis object")



#-------------------------------------------------------------------------
# Class definition
#
class Axis(object):
    """Icepap axis object"""


    def __init__(self, device, address, name="", flags=""):
        """Identifies an axis with its address within the IcePAP device"""

        # Get access to the system
        try:
            hostname = device.hostname()
        except:
            raise ValueError("invalid device object")
        self._system  = device

        # Parse flags
        self._flags   = _parse_flags(flags)

        # The exclusive mode should be defined at group level only
        if self._flags["exclusive"]:
            raise ValueError("invalid option: \"%s\""%EXCLUSIVE)

        # TODO: implement an automatic naming from DSP or automatic
        self._name       = name
        self._address    = address
        self._addrprefix = str(address) + ":"

        # By default not a member of a group
        self._flags["exclusive"] = False
        self._used_in_groups     = []

        #
        self._commands = globals._known_commandlist[hostname] 
          
        # Update the library global resource
        globals._known_axis[self._name] = self


    def name(self):
        return(self._name)

    def address(self):
        return(self._address)

    def system(self):
        return(self._system)

    def groups(self):
        return self._used_in_groups

    def info(self):
        """Returns a string with axis identification information"""
        ret  = ''
        ret += "axis: \"%s\" "%(self.name())
        ret += "system: \"%s\" "%(self.system().hostname())
        ret += "address: \"%s\" "%(self.address())
        return ret

    def diagnostic(self):
        """Returns a string with axis diagnostic information"""
        ret  = ''
        ret += 'WARNING: %s\n'%self.command("?WARNING")
        ret += 'ALARM  : %s\n'%self.command("?ALARM")
        ll   = string.split(self.command("?ISG ?PWRINFO"), '\n')
        ret += 'PWRINFO: '
        for l in ll:
            ret += l + '\n         '
        return ret

    def is_exclusive(self):
        return(self._flags["exclusive"])

    def _append_group(self, group, flags):
        self._used_in_groups.append(group)

        # TODO: handle group flags overwrite rules
        for param in flags.keys():
            if flags[param]:
                self._flags[param] = True

    def _getcommandlist(self):
        answ = self.command("?HELP").splitlines()
        answ = [s for line in answ for s in line.split()]
        return answ

    def set_debug_mode(self, dbgmode):
        self._system.set_debug_mode(dbgmode)

    def is_valid_command(self, comm):
        return comm.split()[0].upper() in self._commands

    def command(self, str_cmd, in_data=None):

        # Minimum check on command syntax
        str_cmd = string.strip(str_cmd)
        if str_cmd[0] == "#":
            return self.ackcommand(str_cmd, in_data)
        else:
            return self._system.command(self._addrprefix + str_cmd, in_data)

    def ackcommand(self, str_cmd, in_data=None):
        # Minimum check on command syntax
        str_cmd = string.strip(str_cmd)
        if str_cmd[0] == "#":
            str_cmd = str_cmd[1:] 
        return self._system.ackcommand(self._addrprefix + str_cmd, in_data)

    def status(self):
        pass

    def pos(self):
        pass

    def move(self):
        pass



#-------------------------------------------------------------------------
# Inteface function
#
def _parse_flags(flags):
    """
    Parse the string with syntax "param=value..." and 
    returns a dictionary
    """

    ret = {}
    ret["exclusive"] = False
    ret["dontmove"]  = False
    ret["readonly"]  = False
    try:
        argins = string.split(string.lower(flags))
    except:
        return ret

    for argin in argins:
        try:
            opt, val = string.split(argin, "=")
        except:
            raise ValueError("invalid option: \"%s\""%argin)
        if opt.startswith("mode"):
            ret["exclusive"] = ("mode=%s"%val == EXCLUSIVE)
            ret["dontmove"]  = ("mode=%s"%val == DONTMOVE)
            ret["readonly"]  = ("mode=%s"%val == READONLY)

    return ret


