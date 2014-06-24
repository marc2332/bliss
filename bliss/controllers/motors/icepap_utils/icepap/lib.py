"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import string
import numpy
import sys
#import pdb


#-------------------------------------------------------------------------
# Specific modules than must be in the PYTHONPATH
#
try:
    import deep.device 
    import deep.log 
except ImportError:
    print 'ERROR: module "deep" not found'
    print 'HINT : add to your PYTHONPATH the location of this module'
    sys.exit(-1)
   

#-------------------------------------------------------------------------
# Constant defintions
#
AXISNAME_FROM_DSP  = "__use_dsp_name"
AXISNAME_AUTO      = "__use_automatic_naming"

EXCLUSIVE          = "mode=exclusive"
READONLY           = "mode=readonly"
DONTMOVE           = "mode=dontmove"

DEBUG1             = "verb=1"
DEBUG2             = "verb=2"
DEBUG3             = "verb=3"

ON                 = True
OFF                = False


#-------------------------------------------------------------------------
# Module resources
#
_known_devices     = {}
_known_commandlist = {}
_known_groups      = {}
_known_axis        = {}


#-------------------------------------------------------------------------
# Inteface function
#
def group_to_name(grp):
    try:
        return grp.name()
    except:
        raise ValueError("invalid group object")


def name_to_group(name):
    try:
        return _known_groups[name]
    except:
        raise ValueError("invalid group name \"%s\""%name)


def axis_to_name(axis):
    try:
        return axis.name()
    except:
        raise ValueError("invalid axis object")


def name_to_axis(name):
    try:
        return _known_axis[name]
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
        for name in _known_axis:
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
        for name in _known_axis:
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
def group_status(grp):
    try:
        return grp.status()
    except:
        raise ValueError("invalid group object")


def group_pos(grp):
    try:
        return grp.pos()
    except:
        raise ValueError("invalid group object")


def group_move(grp, target_positions):
    try:
        return grp.move(target_positions)
    except:
        raise ValueError("invalid group object")


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



#-------------------------------------------------------------------------
# Inteface function
#
def group_command(grp, str_cmd, in_data=None):
    try:
        return grp.command(str_cmd, in_data)
    except:
        raise ValueError("invalid group object")


def axis_command(axis, str_cmd, in_data=None):
    try:
        return axis.command(str_cmd, in_data)
    except:
        raise ValueError("invalid axis object")



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
        if hostname not in _known_devices:
            # Mandatory libdeep argument for IcePAP devices
            argin_str   = ' '.join(["mode=icepap"]+[flags])
            deepdevice  = deep.device.DeepDevice(hostname, argin_str)

            # Save communication payload doing the hypothesis that all
            # axis of an IcePAP device have the same firmare version
            _known_commandlist[hostname] = deepdevice.getcommandlist()

            # Library global resource
            _known_devices[hostname] = deepdevice

        # Object initialization
        self._hostname   = hostname
        self._deepdevice = _known_devices[hostname]
        self._verbose    = deep.log.DBG_ERROR

    def close(self):
        """Close communication links"""
        self._deepdevice.close()
        del _known_devices[self._hostname]

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




#-------------------------------------------------------------------------
# Class definition
#
class Group(object):
    """Icepap group object
 
    g = Group("group_name")   
    g = Group("group_name", [axis1, axis2])   
    g = Group("group_name", [axis1, axis2], EXCLUSIVE)   
    g = Group("group_name", [axis1, axis2], DONTMOVE)   
    g = Group("group_name", flags = READONLY)   

    g.add_axis(axis1)
    g.add_axis(axis1, DONTMOVE)

    g.delete()
    g.delete_all_axis()

    print g.name()
    print g.axis_names()

    l = g.pos()
    l[axis] = 300
    g.pos(l)
    p = g.pos(axis1)
    print "%f" % p
    l = g.pos()
    l = g.pos([axis1, axis2])
    print l.all_axis_str()

    g.set_power(ON)
    g.set_power(OFF, axis1)
    g.set_power(OFF, [axis1, axis2])
    l = g.power()
    print l.all_axis_str()

    l = PosList(...)
    l = g.pos()
    l[axis] = 300
    g.move(l)

    g.stop()
    g.stop(axis1)
    g.stop([axis1, axis2])
    l = AxisList(...)
    g.stop(l)

    while g.ismoving(): time.sleep(.1)

    s = g.status(axis1)
    print "0x%lx" % s
    l = g.status()
    l = g.status([axis1, axis2])
    print "0x%lx" % l[axis1]
    print l.axis_hex(axis1)
    print l.all_axis_hex()
    if status_ismoving(l[axis1]): print "axis moving"

    l = g.command("?ID")
    l = g.command("?ID", axis1)
    l = g.command("?ID", [axis1, axis2])
    print l.all_axis_str() 

    """

    def __init__(self, name, axis_list=None, flags=""):
        """Object constructor"""

        # Group names are unique over the library scope
        try:
            name_to_group(name)
        except ValueError:
            self._name = name
        else:
            raise ValueError("already defined group name \"%s\""%(name))

        # Parse flags and get a dictionnary of booleans
        self._flags     = _parse_flags(flags)

        # A group can be created empty
        self._axis_list = []
        if axis_list:
            # Check that the axis are valid ones
            for axis in axis_list:
                self._check_axis(axis)

            # Append the axis list to the current group
            for axis in axis_list:
                self.add_axis(axis)

        # Update the library global resource
        #_known_groups[name] = weakref.ref(self,tagada)
        _known_groups[name] = self
   

    def ___del__(self):
        """Object destructor"""

        # NOTE MP 13Oct3: avoid implementing the destrucor as this
        # will impact the Python garbage collector. 
        # By the way, any code place here is not guaranteed to be
        # execute when the "del" is used because it may remain
        # references to a group object
        #

    def delete(self):
        """Remove the current group from the ones known by the library"""

        # Inform all group axis that there are now free
        self.delete_all_axis()

        # Update the library global resource
        try:
            del _known_groups[self._name]
        except:
            pass


    def delete_axis(self, axis):
        # TODO
        pass


    def delete_all_axis(self):
        """Remove all the axis from the group"""

        # The has to be emptied
        for idx in range(len(self._axis_list), 0, -1):
            # TODO: inform each axis that it's free (cf handle exclusive)
            axis = self._axis_list[idx-1]
            
            # Remove the reference to the axis
            del self._axis_list[idx-1]


    def _check_axis(self, axis):
        """Raises an exception if axis can not be append to group"""

        # Check object type
        try:
            is_exclusive = axis.is_exclusive()
        except:
            raise ValueError("invalid axis object")

        # Check exclusive flags
        if is_exclusive:
            grp = axis.groups()[0]
            raise ValueError(
                "exclusive axis \"%s\" already used in group \"%s\""%
                (axis.name(), grp.name()))


    def _check_axislist(self, argin):
        """
        Checks that the given axis list is a subset of the current group.
        Returns an axes list or all group axes list if no argin list is given.

        If the argin list is one library type (like PosList), the list
        returned contains only axes.

        Supports also to get a single axis as argument, it will then
        returns a list of one axis element.
        """

        # By default, use all group axis
        if not argin:
            return self._axis_list

        # Supports a single axis argument
        if isinstance(argin, Axis):
            axis_list = [argin]
        else:
            axis_list = argin

        # Check that the given axis belong to the group
        bad_axis_list = [a for a in axis_list if a not in self._axis_list]
        if len(bad_axis_list):
                bad_names = [a.name() for a in bad_axis_list]
                raise ValueError("axis not in the group: %s"% 
                                 ' '.join(bad_names))

        # Always return a pure axes list
        return [a for a in axis_list]


    def _prepare_syscommands(self, axis_list, cmd):
        """
        Returns for each IcePAP system concerned by the given axis list, 
        a command (one per system) and the index (one per axis) within the
        command of each given axis.

        If the axis list is given using a library list type, the values
        associated to the axes will be appended to the IcePAP system
        commands.
        """

        # Prepare the system command
        cmds     = {}
        axis_idx = {}
        sys_idx  = {}
        for axis in axis_list:

            # Handle axis spread over different system
            system = axis.system()
            if not system in cmds:
                cmds[system]    = cmd.upper().strip()
                sys_idx[system] = 0
            cmds[system] += " %s"%(axis.address())
            
            # Append set values for each axis if they have been given
            if isinstance(axis_list, PosList):
                cmds[system] += " %ld"%(axis_list[axis])
            elif isinstance(axis_list, VelList):
                cmds[system] += " %ld"%(axis_list[axis])
            elif isinstance(axis_list, AcctimeList):
                cmds[system] += " %f"%(axis_list[axis])
            # For non supported list type, ignore set values given
            else:
                pass
                
            # Record the index of the axis within the command
            axis_idx[axis]   = sys_idx[system]
            sys_idx[system] += 1

        # Returns a list of IcePAP command per system
        # Returns a list of axes indexes within each above command
        return cmds, axis_idx


    def add_axis(self, axis, flags=""):
        """Append a single axis object to the group"""

        # Check object type
        self._check_axis(axis)

        # Propagate group flags to axis
        axis._append_group(self, self._flags)

        # Append axis to current group
        self._axis_list.append(axis)



    def name(self):
        """Returns the group name as a string"""
        return(self._name)


    def axis_names(self):
        """Returns a list of axis names used in the current group"""
        return [axis.name() for axis in self._axis_list]


    def all_axis(self):
        """Returns all the axis objects of the group"""
        return self._axis_list
        pass


    def command(self, str_cmd, axes=None):
        """
        Send a command, as individual DRIVER command,
        to all group axes or to a given subset list of axes.
        
        Supports also to get a single axis as argument.
        """

        # Minimum check on command syntax
        str_cmd = string.strip(str_cmd)
        if str_cmd[0] == "#":
            return self.ackcommand(str_cmd, in_data)

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Serialize the command on each axis
        ret = AnswerList()
        for axis in axis_list:
            ret[axis] = axis.command(str_cmd)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def ackcommand(self, str_cmd, axes=None):
        """
        Send a command, as individual DRIVER command,
        to all group axes or to a given subset list of axes.
        
        Returns the DRIVERs answers as a list of axis/string pairs.

        Supports also to get a single axis as argument, it will then
        return a single value instead of a list.
        """

        # Minimum check on command syntax
        str_cmd = string.strip(str_cmd)
        if str_cmd[0] == "#":
            str_cmd = str_cmd[1:] 

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Serialize the command on each axis
        ret = AnswerList()
        for axis in axis_list:
            ret[axis] = axis.ackcommand(str_cmd)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def status(self, axes=None):
        """
        Returns a list of axis/status bit mask pairs
        for all group axes or for a given subset list of axes.

        Supports also to get a single axis as argument, it will then
        return a single value instead of a list.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "?FSTATUS")

        # Launch execution on each system 
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])

        # Get unsorted axis status
        stats = {}
        for dev in cmds:
            stats[dev] = string.split(rets[dev])

        # Resort status per axis
        ret = StatusList()
        for axis in axis_list:
            ret[axis] = int(stats[axis.system()][idx[axis]], 16)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def ismoving(self, axis_list=None):
        """Returns true if at least one axis is moving"""

        # Get all axis status
        stats = self.status(axis_list)

        # Check each axis
        for axis in stats:
            if status_ismoving(stats[axis]):
                return True

        # None axis is moving
        return False


    def pos(self, axes=None):
        """
        Returns a list of axis/position pairs 
        for all group axes or for a given subset list of axes.

        Supports also to get a single axis as argument.
        Then a single value will be returned instead of a list.

        Supports also to get a PosList type as argument. 
        Then the positions in the list will be set on the corresponding axes.
        """

        # Get the list of axes, by default use all group axes
        axis_list = self._check_axislist(axes)

        # Set the new positions if given
        if isinstance(axes, PosList):
            cmds, idx = self._prepare_syscommands(axes, "POS")
            for dev in cmds:
                dev.command(cmds[dev])

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "?FPOS")

        # Launch execution on each system 
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])

        # Get unsorted axis status
        pos = {}
        for dev in cmds:
            pos[dev] = string.split(rets[dev])

        # Resort positions per axis
        ret = PosList()
        for axis in axis_list:
            ret[axis] = pos[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def velocity(self, axes=None):
        """
        Returns a list of axis/velocity (in steps/sec) pairs
        for all group axes or for a given subset list of axes.

        Supports also to get a single axis as argument.
        Then a single value will be returned instead of a list.

        Supports also to get a PosList type as argument. 
        Then the velocities in the list will be set on the corresponding axes.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Set the new velocities if given
        if isinstance(axes, VelList):
            cmds, idx = self._prepare_syscommands(axes, "VELOCITY")
            for dev in cmds:
                dev.command(cmds[dev])

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "?VELOCITY")

        # Launch execution on each system 
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])

        # Get unsorted axis velocities
        vel = {}
        for dev in cmds:
            vel[dev] = string.split(rets[dev])

        # Resort positions per axis
        ret = VelList()
        for axis in axis_list:
            ret[axis] = vel[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def acctime(self, axes=None):
        """
        Returns a list of axis/acceleration time (in second) pairs
        for all group axes or for a given subset list of axes.

        Supports also to get a single axis as argument.
        Then a single value will be returned instead of a list.

        Supports also to get a PosList type as argument. 
        Then the times in the list will be set on the corresponding axes.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Set the new acceleration times if given
        if isinstance(axes, AcctimeList):
            cmds, idx = self._prepare_syscommands(axes, "ACCTIME")
            for dev in cmds:
                dev.command(cmds[dev])

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "?ACCTIME")

        # Launch execution on each system 
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])

        # Get unsorted axis acceleration times
        acc = {}
        for dev in cmds:
            acc[dev] = string.split(rets[dev])

        # Resort positions per axis
        ret = AcctimeList()
        for axis in axis_list:
            ret[axis] = acc[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret



    def stop(self, axes=None):
        """
        Requests to stop motions on all group axes
        or for a given subset list of axes.

        Supports also to get a single axis as argument.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "STOP")

        # Launch execution on each system but
        # without ack to not serialize executions
        for dev in cmds:
            dev.command(cmds[dev])
        
        # Normal end
        return 


    def set_power(self, action, axes=None):
        """
        Switch on/off the power, according to boolean action,
        on all group axes or on a given subset list of axes.

        Supports also to get a single axis as argument.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # The argument must be a boolean
        try:
            pwr = {True: "ON", False: "OFF"}[action]
            cmd = "POWER %s"%pwr
        except:
            raise ValueError("invalid action, must be boolean")

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, cmd)

        # Launch execution on each system with ack
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])
        
        # Check execution:
        # A returned "OK" doesn't mean that the power has been set on 
        # the axis but that there is no reasons to not try to set it.
        # The system command returns on the first not "OK" axis.
        for dev in rets:
            if rets[dev] != "OK":
                raise RuntimeError(
                    'unable to switch power %s on system \"%s\"'%
                    (pwr, dev))

        # Check that power has been well set
        power_states = self.power(axis_list)
        error_msg    = ''
        for axis in axis_list:
            if power_states[axis] != pwr:
                # Prepare information on faulty axis
                error_msg += 'unable to switch power %s on %s\n'% \
                    (pwr, axis.info())

                # Get diagnostic information
                error_msg += axis.diagnostic()

        # If several axes had a wrong power, raise only one exception
        if len(error_msg):
            raise RuntimeError(error_msg)

        # Normal end
        return 


    def power(self, axes=None):
        """
        Returns a list of axis/string pairs describing power state
        for all group axes or for a given subset list of axes.

        Supports also to get a single axis as argument, it will then
        return a single value instead of a list.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Prepare the commands to send to each concerned system
        cmds, idx = self._prepare_syscommands(axis_list, "?POWER")

        # Launch execution on each system 
        rets = {}
        for dev in cmds:
            rets[dev] = dev.ackcommand(cmds[dev])

        # Get unsorted axis status
        stat = {}
        for dev in cmds:
            stat[dev] = string.split(rets[dev])

        # Resort positions per axis
        ret = AnswerList()
        for axis in axis_list:
            ret[axis] = stat[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, Axis):
            return ret[axes]

        # Normal end
        return ret


    def move(self, target_positions):
        """Move the list of motors to the specified absolute positions"""

        # Check target argin type
        try:
            axis_list = target_positions.keys()
        except:
            raise ValueError("invalid argument: wrong target object")

        # Prepare the motion command
        cmds={}
        for axis in axis_list:

            # Check axis argin type
            try:
                system = axis.system()
            except:
                raise ValueError("invalid argument: wrong axis object")

            # Check that axis belongs to the current group
            if not axis in self._axis_list:
                raise ValueError("invalid argument: axis not in this group")

            # TODO: Check axis flags compatible with motion

            # Handle axis spread over different system
            if not system in cmds:
                cmds[system] = "MOVE GROUP"
            cmds[system] += " %s %ld"% \
                (axis.address(), target_positions[axis])
        
        # Launch the motions on each concerned system
        for dev in cmds:
            dev.ackcommand(cmds[dev])
        
        # Normal end
        return 


    def rmove(self, target_positions):
        # TODO
        pass

    def pmove(self, param_value, axis_list):
        # TODO
        pass






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
        self._commands = _known_commandlist[hostname] 
          
        # Update the library global resource
        _known_axis[self._name] = self


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
# Class definition
#
class AxisList(list):
    """List of axis objects

    l=AxisList(axis1, axis2)
    l=AxisList()
 
    l.append(axis3)
    print l.axis_names()

    """

    def __init__(self, *args):
        """Standard list construcor"""

        # Will raise an exception if axis is a wrong object
        for axis in args:
            axis_to_name(axis)

        # Let the underlying list class do the job
        super(AxisList, self).__init__(args)

    def append(self, axis):
        """Append an axis"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying list class do the job
        list.append(self, axis)

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in list(self)]



#-------------------------------------------------------------------------
# Class definition
#
class PosList(dict):
    """List of axis/position pairs

    l=PosList([axis1, 100.1])
    l=PosList()

    l[axis1] = 100.1
    l[axis2] = 200.2
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, position in args:
            axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(PosList, self).__init__(args)

    def __setitem__(self, axis, pos):
        """Append a pair of axis/position"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.double(pos))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and position"""

        # Convert postions from float to int just for display
        return "%s:%ld"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and position"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])



#-------------------------------------------------------------------------
# Class definition
#
class VelList(dict):
    """List of axis/velocity pairs

    l=VelList([axis1, 2000])
    l=VelList()

    l[axis1] = 2000
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, velocity in args:
            axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(VelList, self).__init__(args)

    def __setitem__(self, axis, vel):
        """Append a pair of axis/velocity"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        # Warning: the velocity returned by IcePAP can be in scientific 
        # notation which is not readable with pure int()
        dict.__setitem__(self, axis, int(float(vel)))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and velocity"""
        return "%s:%ld"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and velocities"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])




#-------------------------------------------------------------------------
# Class definition
#
class AcctimeList(dict):
    """List of axis/acceleration time pairs

    l=AcctimeList([axis1, 0.125])
    l=AcctimeList()

    l[axis1] = 0.125
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, acctime in args:
            axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(AcctimeList, self).__init__(args)

    def __setitem__(self, axis, acctime):
        """Append a pair of axis/acceleration time"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.double(acctime))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and acceleration time"""
        return "%s:%f"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and acceleration times"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])



#-------------------------------------------------------------------------
# Class definition
#
class StatusList(dict):
    """List of axis/status pairs

    l=StatusList([axis1, 0xaabbccdd])
    l=StatusList()

    l[axis1] = 0xaabbccdd
    l[axis2] = 0xdefecada
  
    print l.axis_hex(axis2)
    print l.all_axis_hex()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, status in args:
            axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(StatusList, self).__init__(args)

    def __setitem__(self, axis, sta):
        """Append a pair of axis/status"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.uint32(sta))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_hex(self, axis):
        """Returns a string with axis name and hexadecimal status"""
        return "%s:0x%08x"%(axis.name(), self[axis])

    def all_axis_hex(self):
        """Returns a string with all axis names and hexadecimal status"""
        return ' '.join([self.axis_hex(a) for a in dict.keys(self)])



#-------------------------------------------------------------------------
# Class definition
#
class AnswerList(dict):
    """List of axis/string pairs 

    l=AnswerList()

    l[axis1] = "blabla"
    l = g.command("?ID")
    
    print l.axis_str(axis2)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, str in args:
            axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        super(AnswerList, self).__init__(args)

    def __setitem__(self, axis, str):
        """Append a pair of axis/string"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, str)

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and string"""
        return "%s:%s"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and strings"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])
