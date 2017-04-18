"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import string


#-------------------------------------------------------------------------
# Library modules
#
import globals
import axis  as libaxis
import types as libtypes



#-------------------------------------------------------------------------
# Constant defintions
#
ON                 = True
OFF                = False


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
        return globals._known_groups[name]
    except:
        raise ValueError("invalid group name \"%s\""%name)

def group_exists(name):
    return name in globals._known_groups


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


def group_command(grp, str_cmd, in_data=None):
    try:
        return grp.command(str_cmd, in_data)
    except:
        raise ValueError("invalid group object")




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
        self._flags     = libaxis._parse_flags(flags)

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
        globals._known_groups[name] = self
   

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
            del globals._known_groups[self._name]
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
        if isinstance(argin, libaxis.Axis):
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
            if isinstance(axis_list, libtypes.PosList):
                cmds[system] += " %ld"%(axis_list[axis])
            elif isinstance(axis_list, libtypes.VelList):
                cmds[system] += " %ld"%(axis_list[axis])
            elif isinstance(axis_list, libtypes.AcctimeList):
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
        ret = libtypes.AnswerList()
        for axis in axis_list:
            ret[axis] = axis.command(str_cmd)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
        ret = libtypes.AnswerList()
        for axis in axis_list:
            ret[axis] = axis.ackcommand(str_cmd)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
        ret = libtypes.StatusList()
        for axis in axis_list:
            ret[axis] = int(stats[axis.system()][idx[axis]], 16)

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
            return ret[axes]

        # Normal end
        return ret


    def warning(self, axes=None):
        """
        Returns a list of axis/warning conditions pairs
        for all group axes or for a given subset list of axes.

        A warning condition is a string with multiple CR separated lines.

        Supports also to get a single axis as argument, it will then
        return a single value instead of a list.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Get unsorted axis status
        # No system command available, therefore interogate axis per axis
        warns = {}
        for axis in axis_list:
            warns[axis] = axis.ackcommand("?WARNING")

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
            return warns[axes]

        # Normal end
        return warns


    def alarm(self, axes=None):
        """
        Returns a list of axis/alarm conditions pairs
        for all group axes or for a given subset list of axes.

        An alarm condition is a string with multiple CR separated lines.

        Supports also to get a single axis as argument, it will then
        return a single value instead of a list.
        """

        # Get the list of axis, by default use all group axis
        axis_list = self._check_axislist(axes)

        # Get unsorted axis status
        # No system command available, therefore interogate axis per axis
        alarms = {}
        for axis in axis_list:
            alarms[axis] = axis.ackcommand("?ALARM")

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
            return alarms[axes]

        # Normal end
        return alarms


    def ismoving(self, axis_list=None):
        """Returns true if at least one axis is moving"""

        # Get all axis status
        stats = self.status(axis_list)

        # Check each axis
        for axis in stats:
            if libaxis.status_ismoving(stats[axis]):
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
        if isinstance(axes, libtypes.PosList):
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
        ret = libtypes.PosList()
        for axis in axis_list:
            ret[axis] = pos[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
        if isinstance(axes, libtypes.VelList):
            cmds, idx = self._prepare_syscommands(axes, "VELOCITY")
            for dev in cmds:
                dev.ackcommand(cmds[dev])

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
        ret = libtypes.VelList()
        for axis in axis_list:
            ret[axis] = vel[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
        if isinstance(axes, libtypes.AcctimeList):
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
        ret = libtypes.AcctimeList()
        for axis in axis_list:
            ret[axis] = acc[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
        ret = libtypes.AnswerList()
        for axis in axis_list:
            ret[axis] = stat[axis.system()][idx[axis]]

        # For a single axis request, return a single value rather than a list
        if isinstance(axes, libaxis.Axis):
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
            try:
                pos = int(target_positions[axis])
            except ValueError:
                return
            cmds[system] += " %s %ld"% \
                (axis.address(), pos)
        
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





