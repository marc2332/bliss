"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import string
import time


#-------------------------------------------------------------------------
# Library modules
#
import globals
import axis   as libaxis
import groups as libgroups
import types  as libtypes
import vdata  as libvdata

import deep.log as log


#-------------------------------------------------------------------------
# Class definition
#
class Trajectory(object):
    """Icepap trajectory object

    # empty trajectory object
    # identified by its mandatory name
    # and unique within the library 
    t = Trajectory("name")   

    # parameter range is a list
    parameter_list = range(0, 100, 2)  
    t = Trajectory("name", parameter_list)   

    # error if non empty trajectory object
    parameter_list = range(100)
    t.set_parameter(parameter_list)

    # returns a list
    print t.get_parameter() 

    # empty an existing trajectory object
    t.drain()

    # the list must have the same range than parameter
    position_list = list(...)
    t.add_axis_trajectory(axis, position_list)
    t.add_axis_trajectory(axis, position_list, ovewrite=True)

    # use first column range for the trajectory object if not yet set (!!!!)
    t = Trajectory("name")   
    t.add_axis_trajectory(axis, position_list)

    # optional optimization criterion
    position_list = list(...)
    t.add_axis_trajectory(axis, position_list, optimzation=True, precision=0.1)

    # optional slope list
    position_list = list(...)
    slope_list = list(...)
    t.add_axis_trajectory(axis, position_list, slope_list)

    # set parameter acceleration time and velocity,
    # accepted even on a trajectory without axis trajectories
    t = Trajectory("name")   
    t.acctime(new_acctime)
    t.velocity(new_velocity)
    print t.acctime()
    print t.velocity()



    #
    # Motion using direct trajectory object (DONE)
    #

    t.sync(parameter)
    t.move(parameter) 
    t.move(parameter, wait=False) 
    t.pos() 
    t.pos(axis) 
    t.pos(axis_list) 
    t.stop()
    t.load()
    t.load(axis)
    t.load(axes_list)
    t.status()
    t.ismoving()



    #
    # Motion using group implementation (TODO)
    #

    # retrieve information from an existing trajectory object
    (param_list, pos_list, slope_list) = t.get_axis_trajectory(axis)
    param_list = t.get_axis_trajectory(axis, type="parameter")
    post_list  = t.get_axis_trajectory(axis, type="position")
    (axis1, axis2) = t.getAxes()

    # before moving over a trajectory, the axes must be put on it
    #    -done over a group
    #    -axes will physically move
    g = t.get_axes_group()
    g.trajectory_sync(t, parameter)
    g.trajectory_sync(t, parameter, axis)
    g.trajectory_sync(t, parameter, axis_list)

    # launching motion over a trajectory 
    #    -done over a group
    #    -if the axes are on several systems, the lib will split the
    #     trajectory columns
    #    -the trajectory is downloaded into the DRIVERs at first motion
    #    -the download could be skipped if already downloaded (use trajectory
    #     name for identification)
    #    -the optional compression is hidden to user
    #    -by default all axes will move
    g = t.get_axes_group()
    g.trajectory_move(t, parameter)
    g.trajectory_move(t, parameter, axis)
    g.trajectory_move(t, parameter, axis_list)

    # the trajectory download can be forced
    #    -done over a group (not mandatory but more homogeneous, separate
    #     trajectories preparation from actions using them
    #    -the lib keeps in memory which axes have already the trajectory
    #     in their memory (cf identify trajectories be name as there is
    #     no ID in DSP firmware)
    g = t.get_axes_group()
    g.trajectory_load(t)
    g.trajectory_load(t, axis)
    g.trajectory_load(t, axis_list)
    


    #
    # Advanced feature (TODO)
    #

    # the transfer mode is part of the trajectory properties
    #    -need to handler different transfer modes for axes (????)
    #    -exemple of modes:
    #       -AUTO: (default) user let the lib free to process data/load
    #       -RAW: no data manipulation
    #       -SYNCHRONOUS: trajectories loaded all at once (????) 
    #        or at definition time (????)
    t.set_transfert_mode(mode)
    t.get_transfert_mode(mode)

    # how to handle parameter tracking (?????)
    t.tracking_start()
    t.tracking_start(axis)
    t.tracking_start(axis_list)
    t.tracking_stop()

    # returns internal lists, for debugging only
    t._get_column(axis)
    t._get_column(axis, type="derivative")
    t._get_columnPos(axis)
    t._get_columnDrv(axis)

    # handle internal parameters of a trajectory object
    d = t._get_internals()
    print d["usingsyscmds"]
    ...
    t._set_internals({'usingyscmds' : True})
    ...

    # handle internal parameters of an axis trajectory object
    d = t._get_internals(axis)
    print d["optimization"]
    print d["precision"]
    print d["compressed_size"]
    ...

    """


    def __init__(self, name, range_list=None):
        """Object constructor"""

        # TODO: keep a library centralized list of trajectories
        # TODO: keep a library centralized information on downloaded
        # trajectories to DRIVERs
        self._name = name

        # empty internals
        self.drain()

        # The parameter range is given as a list
        if range_list is not None:
            self.set_parameter(range_list)


    def __del__(self):
        # TODO: remove trajectory name from centralized storage
        self.drain()
        pass


    def drain(self):
        """Emptying the trajectory"""

        # new default internals
        self._internals   = {}
        self._internals["usingsyscmds"] = True

        # new empty trajectory
        self._param_range = {}
        self._pos_columns = {}
        self._drv_columns = {}
        self._axis_list   = []
        self._loaded      = {}
        self._sync        = {}
        self._acctime     = 0.1
        self._velocity    = 1.0


        # TODO: remove previous vdata from memory
        self._vdata        = libvdata.vdata()

        # Empty internal trajectory optimization parameter
        self._opt_params  = {}

        # Empty group
        self._group = None


    def _update_group(self, axis_list=None):
        """Update internal group object with given moving axis"""
        if self._group:
            self._group.delete()
        if axis_list is not None:
            if libgroups.group_exists(self._name):
                g = libgroups.name_to_group(self._name)
                g.delete()
            self._group = libgroups.Group(self._name, axis_list)


    def velocity(self, new_vel=None):
        """
        Returns the parameter velocity in parameter units/seconds.
        If a new velocity is given, it will be set.
        """

        if new_vel is not None:
            self._set_velocity(new_vel)

        return self._get_velocity()


    def _set_velocity(self, new_vel=None):
        """Sets the parameter velocity given in parameter units/seconds"""

        # Minium check
        if new_vel is None:
            raise ValueError("Missing parameter velocity")

        # If the trajectory has not been loaded yet on a axis, 
        # the parameter acceleration and velocity can not be set
        # Therefore, memorize acceleration and velocity 
        # to set them at the sync() time.
        self._velocity = new_vel
        if len(self._axis_list) == 0:
            return

        # By default set parameter velocity on all axes
        axis_list = self._check_axislist()

        # Prepare the systems commands
        cmd  = "PARVEL %f" % new_vel
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s" % axis.address()

        # Launch commands on systems
        for dev in cmds:
            #TODO: check answer
            dev.ackcommand(cmds[dev])


    def _get_velocity(self):
        """Returns the parameter velocity given in parameter units/seconds"""

        # Allows client to get acceleration time and velocity
        # on an empty trajectory object
        if len(self._axis_list) == 0:
            return self._velocity

        # By default set parameter velocity on all axes
        axis_list = self._check_axislist()

        # Prepare the systems commands
        cmd  = "?PARVEL"
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s" % axis.address()

        # Launch commands on systems
        pars = []
        for dev in cmds:
            ans = dev.ackcommand(cmds[dev])

            # The parameter value should be the same for all axes
            # therefore no need to identify axes
            vals = string.split(ans)
            for val in vals:
                pars.append(float(val))

        # The parameter value should be the same on all axes
        par_val = pars[0]
        for par in pars:
            if par != par_val:
                raise RuntimeError("discrpancy on parameter velocities")

        # Normal end
        return par_val


    def acctime(self, new_acctime=None):
        """
        Returns the parameter accleration time in seconds.
        If a new acceleration is given, it will be set.
        """
        if new_acctime is not None:
            self._set_acctime(new_acctime)

        return self._get_acctime()


    def _set_acctime(self, new_acctime=None):
        """Sets the parameter acceleration time given in seconds"""

        # Minium check
        if new_acctime is None:
            raise ValueError("Missing parameter acceleration time")

        # If the trajectory has not been loaded yet on a axis, 
        # the parameter acceleration and velocity can not be set
        # Therefore, memorize acceleration and velocity 
        # to set them at the sync() time.
        self._acctime = new_acctime
        if len(self._axis_list) == 0:
            return

        # By default set parameter acceleration on all axes
        axis_list = self._check_axislist()

        # Prepare the systems commands
        cmd  = "PARACCT %f" % new_acctime
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s" % axis.address()

        # Launch commands on systems
        for dev in cmds:
            #TODO: check answer
            dev.ackcommand(cmds[dev])


    def _get_acctime(self):
        """Returns the parameter acceleration time given in seconds"""

        # Allows client to get acceleration time and velocity
        # on an empty trajectory object
        if len(self._axis_list) == 0:
            return self._acctime

        # By default set parameter acceleration on all axes
        axis_list = self._check_axislist()

        # Prepare the systems commands
        cmd  = "?PARACCT"
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s"%(axis.address())

        # Launch commands on systems
        pars = []
        for dev in cmds:
            ans = dev.ackcommand(cmds[dev])

            # The parameter value should be the same for all axes
            # therefore no need to identify axes
            vals = string.split(ans)
            for val in vals:
                pars.append(float(val))

        # The parameter value should be the same on all axes
        par_val = pars[0]
        for par in pars:
            if par != par_val:
                raise RuntimeError("discrpancy on parameter accel times")

        # Normal end
        return par_val



    def get_parameter(self):
        """Returns the parameter range as a list"""
        return self._param_range


    def set_parameter(self, range_list):
        """Set the parameter range given as a list"""
        if(len(self._param_range)):
            raise ValueError("non empty trajectory object")

        # keep a copy of the list for faster retrieving
        self._param_range = range_list
        self._update_vdata()


    def _get_internals(self, axis=None):
        """
        For development only
        
        Returns a dictionary with internal parameters 
        of the current tracjectory object or the given axis
        """
        if axis is None:
            return self._internals
        else:
            raise RuntimeError("not implemented yet")


    def _set_internals(self, newparams):
        """
        For development only

        Use the given dictionary to change internal parameters
        of the curent trajectory object
        """

        for param in newparams:
            if param not in self._internals:
                raise ValueError("invalid parameter \"%s\"", param)
            self._internals[param] = newparams[param]


    def add_axis_trajectory(self, axis, pos_list, drv_list=None):
        """
        Add a new axis to the trajectory

        The position and derivative lists must have the same
        range than the current trajectory parameter

        TODO: optional optimization parameters to store in dictionary
        """

        # Will raise an exception if axis is a wrong object
        axis_name = libaxis.axis_to_name(axis)

        # Overwriting an already defined axis is forbidden
        # TODO: handler "overwrite" optional argin
        if axis in self._axis_list:
            raise ValueError("trajectory already defined for axis: %s"%
                axis_name)

        # Minium check on argins
        if(type(pos_list) != list):
            raise ValueError("invalid positions list type")

        # Minium check on argins
        if(drv_list != None):
            if(type(drv_list) != list):
                raise ValueError("invalid derivative list type")

        # If parameter range not yet define, use the first column range
        if(self._param_range == None):
            self._param_range = range(len(pos_list))

        # Check argin range
        if(len(pos_list) != len(self._param_range)):
            raise ValueError("invalid position list range, must be: %d"%
                len(self._param_range))

        # Check argin range
        if(drv_list != None):
            if(len(drv_list) != len(self._param_range)):
                raise ValueError("invalid derivative list range, must be: %d"%
                    len(self._param_range))

        # Store new columns
        self._pos_columns[axis] = pos_list
        if(drv_list != None):
            self._drv_columns[axis] = drv_list

        # Update list of axes
        if axis not in self._axis_list:
            self._axis_list.append(axis)

        # Update data vector
        self._update_vdata(axis)

        # The trajectory has to be loaded or reloaded
        self._loaded[axis] = False
        self._sync[axis]   = False


    def _update_vdata(self, axis = None):
        """Update internal data vector for the given axis object"""


        # TODO: axis trajectory already defined

        # append an axis trajectory
        if axis is None:
            log.trace("updating parameter")

            # append mandatory parameter data 
            self._vdata.append(
                self._param_range, 
                int(libvdata.ADDRUNSET),
                libvdata.PARAMETER)
        else:
            log.trace("updating trajectory for axis: %s" % axis.name())

            # append mandatory position data
            self._vdata.append(
                self._pos_columns[axis], 
                int(axis.address()),
                libvdata.POSITION)

            # optional slope data
            if(axis in self._drv_columns):
                self._vdata.append(
                    self._drv_columns[axis], 
                    int(axis.address()),
                    libvdata.SLOPE)

        # normal end
        self._vdata.loginfo()


    def load(self, axes=None):
        """Force trajectory download into the IcePAP system"""

        # By default load all axes
        axis_list = self._check_axislist(axes)

        # Download trajectory 
        if(self._internals["usingsyscmds"] is True):
            return self._load_using_syscmds(axis_list)
        else:
            return self._load_using_axiscmds(axis_list)


    def _load_using_axiscmds(self, axis_list):
        """
        Force trajectory download into the IcePAP system
        using IcePAP axis commands
        """

        for axis in axis_list:
            cmd = "%d:*PARDAT"%int(axis.address())
            axis.system().ackcommand(cmd, self._vdata.bin())
            self._loaded[axis] = True

    def _load_using_syscmds(self, axis_list):
        """
        Force trajectory download into the IcePAP system
        using IcePAP system commands
        """

        # Prepare the systems commands
        cmd  = "*PARDAT"
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd

        # Launch commands on systems
        for dev in cmds:
            #TODO: check answer
            dev.ackcommand(cmds[dev], self._vdata.bin())

        # Remimbers download done
        for axis in axis_list:
            self._loaded[axis] = True


    def sync(self, parameter, axes=None, wait=True):
        """
        Put axes on a trajectory, 
        warning: the concerned axes will physically move

        If no axes are given, all axes currently defined in the 
        trajectory object will move

        A subset list of axes can be given

        A single axis can also be given
        """
        # Get the list of axes to move
        axis_list = self._check_axislist(axes)

        # Minimum check
        self._check_loaded(axis_list)

        # Ensure that parameter acceleration time and velocity are
        # set for all axes. Note: set first velocity because the
        # acceleration time is recalculated
        self._set_velocity(self._velocity)
        self._set_acctime(self._acctime)

        # Prepare the systems commands
        cmd  = "MOVEP %f"%(parameter)
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s"%(axis.address())

        # Launch commands on systems
        for dev in cmds:
            dev.ackcommand(cmds[dev])

        # Update internal group for further axes access
        self._update_group(axis_list)

        # Wait for the end of the motion
        if wait:
            while self._group.ismoving():
                time.sleep(.01)

        # TODO: check acknowledgements
        for axis in axis_list:
            self._sync[axis] = True


    def move(self, parameter, axes=None, wait=True):
        """
        Launching motion over a trajectory

        If no axes are given, all axes currently defined in the 
        trajectory object will move

        A subset list of axes can be given

        A single axis can also be given
        """

        # Minimum checks trajectory object state
        if(self._param_range == None):
            raise ValueError("non initialized parameter range")
        if(len(self._param_range) == 0):
            raise ValueError("wrong parameter range")
        if(len(self._pos_columns) == 0):
            raise ValueError("non initialized trajectory, missing axis column")

        
        # Get the list of axes to move
        axis_list = self._check_axislist(axes)

        # Minimum check
        self._check_loaded(axis_list)
        self._check_sync(axis_list)

        # Prepare the systems commands
        cmd  = "PMOVE %f"%(parameter)
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s"%(axis.address())

        # Launch commands on systems
        # TODO: check acknowledgements
        for dev in cmds:
            dev.ackcommand(cmds[dev])

        # Wait for the end of the motion
        if wait:
            g = libgroups.Group("tmp", axis_list)
            while g.ismoving():
                time.sleep(.01)
            g.delete()


    def stop(self, axes=None):
        """Stop any trajectory motion
        """

        # Get the list of axes to move
        axis_list = self._check_axislist(axes)

        # Prepare the systems commands
        cmd  = "STOP"
        cmds = {}
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s"%(axis.address())

        # Launch commands on systems
        for dev in cmds:
            dev.ackcommand(cmds[dev])


    def pos(self, axes=None):
        """
        Returns the current position on the trajectory.
        The position is a parameter value.
        """

        # Get the list of axes to access
        axis_list = self._check_axislist(axes)

        # Minimum check
        self._check_loaded(axis_list)
        self._check_sync(axis_list)

        # Prepare the systems commands
        cmd  = "?PARPOS"
        cmds = {}
        pars = []
        for axis in axis_list:

            # A command per system
            system = axis.system()
            if not system in cmds:
                cmds[system] = cmd
            cmds[system] += " %s"%(axis.address())

        # Launch commands on systems
        for dev in cmds:
            ans = dev.ackcommand(cmds[dev])

            # The parameter value should be the same for all axes
            # therefore no need to identify axes
            vals = string.split(ans)
            for val in vals:
                pars.append(float(val))

        # TODO: remove this verification and trust IcePAP 
        par     = pars[0]
        return par
        par_min = float("inf")
        par_max = 0
        for par in pars:
            if par < par_min:
                par_min = par
            if par > par_max:
                par_max = par
        if par_max == par_min == par:
            pass
        else:
            raise RuntimeError("discrpancy on parameter pos")

        # Normal end
        return par


    def status(self):
        """
        Returns an IcePAP status bitmask

        There is no command to get a parameter status
        therefore emulate the bitmask from all axes bitmaks.
        """
        ret  = 0
        stats = self._group.status()
        for axis in stats:
            stat = stats[axis]
            ret  = libaxis.status_set_ismoving(
                ret, libaxis.status_ismoving(stat))
            ret  = libaxis.status_set_isready(
                ret, libaxis.status_isready(stat))

        # Return a unique status value
        return ret

    def ismoving(self):
        """Returns true if at least one axis is moving"""
        return libaxis.status_ismoving(self.status())


    def _check_axislist(self, argin=None):
        """
        Returns always a list of axes that will belong
        to the current trajectory object.

        If no argin is given, all axes of the trajectory will be returned.

        If a list of axes is given, returns the same list after checking
        the axes objects.

        A single axis object can also be given as argin.
        """

        # Minimum check
        if len(self._axis_list) == 0:
            raise ValueError("empty trajectory object")

        # By default, use all trajectory known axes
        if(argin is None):
            return self._axis_list

        # Supports a single axis argument
        if isinstance(argin, libaxis.Axis):
            axis_list = [argin]
        else:
            axis_list = argin


        # Check that the given axis belongs to current trajectory
        bad_axis_list = [a for a in axis_list if a not in self._axis_list]
        if len(bad_axis_list):
            bad_names = [a.name() for a in bad_axis_list]
            raise ValueError("axes not in the trajectory: %s"%
                ' '.join(bad_names))

        # Always return a pure axes list
        return [a for a in axis_list]


    def _check_loaded(self, axis_list):
        """Check for the list of axes given that
        the trajectory has already been loaded

        Will raise an exception otherwise
        """

        # Faster check than letting DSP do the check
        for axis in axis_list:
            try:
                loaded = self._loaded[axis]
            except:
                loaded = False
            if not loaded:
                raise RuntimeError('trajectory not loaded for axis: %s'%
                    axis.name())

        # Normal end
        return


    def _check_sync(self, axis_list):
        """Check for the list of axes given that
        the axes are on their trajectory

        Will raise an exception otherwise
        """

        # Faster check than letting DSP do the check
        for axis in axis_list:
            try:
                sync = self._sync[axis]
            except:
                sync = False
            if not sync:
                raise RuntimeError('missing trajectory sync for axis: %s'%
                    axis.name())

        # Normal end
        return

