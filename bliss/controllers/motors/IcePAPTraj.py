import sys
import os

"""
Bliss generic library
"""
from bliss.controllers.motor import Controller; from bliss.common import log, axis
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState
import bliss

"""
Extra modules
"""
import libicepap

"""
Global resources
"""
_ICEPAP_TAB = "IcePAP: "


class IcePAPTraj(Controller):

    """Implement IcePAP stepper motor controller access"""
    default_group = None

    def __init__(self, name, config, axes, encoders):
        """Contructor"""
        Controller.__init__(self, name, config, axes, encoders)

        # Records the list of axes
        self.axes_names = []
        self.axis_list  = {}

        # Underlying libicepap object
        self.libdevice = {}
        self.libtraj   = {}


    def initialize(self):
        """Controller initialization"""
        self.log_info("initialize() called")

        # Optional parameters
        try:
            self.libdebug = int(self.config.get("libdebug"))
        except:
            self.libdebug = 1


       
    def finalize(self):
        """Controller no more needed"""
        self.log_info("finalize() called")
        

    def initialize_axis(self, axis):
        """Axis initialization"""
        self.log_info("initialize_axis() called for axis %r" % axis.name)

        # Get the list of IcePAP axes
        axes_names = axis.config.get("axislist").split()
        if len(axes_names) == 0:
            raise ValueError('missing mandatory config parameter "axislist"')

        # Check the list of IcePAP axes
        dev = None
        for axis_name in axes_names:

            # Get EMotion axis object
            hw_axis = bliss.get_axis(axis_name)

            # Check that it's an IcePAP controlled one
            if type(hw_axis.controller).__name__ is not 'IcePAP':
                raise ValueError('invalid axis "%s", not an IcePAP'%axis_name)

            # Get underlying libicepap object
            axis_dev = hw_axis.controller.libdevice
            if dev is None:
                dev = axis_dev

            # Let's impone that the trajectories work only on the same system
            if axis_dev.hostname() != dev.hostname():
                raise ValueError( 
                    'invalid axis "%s", not on the same IcePAP'%axis_name)

        # At this point we have configuration
        # Create an empty libicepap trajectory object
        self.libtraj[axis] = libicepap.Trajectory(axis.name)

        # Keep a record of axes
        for axis_name in axes_names:
            self.axes_names.append(axis_name)
            hw_axis = bliss.get_axis(axis_name)
            self.axis_list[axis_name] = hw_axis

        # Keep a record of the IcePAP system for faster access
        self.libdevice = dev

        # Add new axis oject methods
        add_axis_method(axis, self.set_parameter)
        add_axis_method(axis, self.get_parameter)
        add_axis_method(axis, self.set_trajectory)
        add_axis_method(axis, self.drain)
        add_axis_method(axis, self.load)
        add_axis_method(axis, self.sync)


    def read_position(self, axis, measured=False):
        """Returns axis position in motor units"""
        self.log_info("position() called for axis %r" % axis.name)
        return self.libtraj[axis].pos()


    def set_position(self, axis, new_pos):
        raise RuntimeError('unavailable for a trajectory')


    def read_velocity(self, axis):
        """Returns axis current velocity in user units/sec"""
        return self.libtraj[axis].velocity()


    def set_velocity(self, axis, new_velocity):
        """Set axis velocity given in units/sec"""
        self.log_info("set_velocity(%f) called for axis %r" %
                      (new_velocity, axis.name))
        self.libtraj[axis].velocity(new_velocity)

        # Always return the current velocity
        return self.read_velocity(axis)


    def read_acceleration(self, axis):
        """Returns axis current acceleration in steps/sec2"""
        acctime  = self.libtraj[axis].acctime()
        velocity = self.read_velocity(axis)
        return velocity/acctime


    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in steps/sec2"""
        self.log_info("set_acceleration(%f) called for axis %r" %
                      (new_acc, axis.name))
        velocity     = self.read_velocity(axis)
        new_acctime  = velocity/new_acc

        self.log_info("set_acctime(%f) called for axis %r" %
                      (new_acctime, axis.name))
        self.libtraj[axis].acctime(new_acctime)

        # Always return the current acceleration
        return self.read_acceleration(axis)


    def state(self, axis):
        """Returns the current axis state"""
        self.log_info("state() called for axis %r" % axis.name)

        # Get a unique status for all IcePAP axes
        status = self.libtraj[axis].status()
        self.log_info("hardware status got: 0x%08x" % status)

        # Convert status from icepaplib to bliss format.
        _state = AxisState()
        if(libicepap.status_ismoving(status)):
            self.log_info("status MOVING")
            _state.set("MOVING")
            return _state

        if(libicepap.status_isready(status)):
            self.log_info("status READY")
            _state.set("READY")

            if(libicepap.status_lowlim(status)):
                _state.set("LIMNEG")

            if(libicepap.status_highlim(status)):
                _state.set("LIMPOS")

            if(libicepap.status_home(status)):
                _state.set("HOME")

            return _state

        # Abnormal end
        return AxisState("FAULT")


    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        self.log_info("prepare_move(%fsteps) called for axis %r" %
            (motion.target_pos, motion.axis.name))
        pass


    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        self.log_info("start_one(%fsteps) called for axis %r" % 
            (motion.target_pos, motion.axis.name))
        self.libtraj[motion.axis].move(motion.target_pos, wait=False)


    def start_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately,
        positions in motor units
        """
        self.log_info("start_all() called")
        pass


    def stop(self, axis):
        """Stops smoothly an axis motion"""
        self.log_info("stop() called for axis %r" % axis.name)
        self.libtraj[axis].stop()


    def stop_all(self, *motion_list):
        """Stops smoothly all the moving axis given"""
        self.log_info("stop_all() called")
        for motion in motion_list:
            self.libtraj[motion.axis].stop()


    def home_search(self, axis):
        """Launch a homing sequence"""
        raise RuntimeError('unavailable for a trajectory')


    def home_state(self, axis):
        """Returns the current axis state while homing"""
        raise RuntimeError('unavailable for a trajectory')


    def limit_search(self, axis, limit):
        """
        Launch a limitswitch search sequence
        the sign of the argin gives the search direction
        """
        raise RuntimeError('unavailable for a trajectory')


    def log_level(self, lvl):
        """Changes IcePAP and eMotion libraries verbose level"""

        # Change in the eMotion library
        log.level(lvl)

        # Value mapping between the two libraries
        #        eMotion == IcePAP
        #   NOTSET ==  0 == 0 == DBG_NONE
        #   DEBUG  == 10 == 4 == DBG_DATA
        #   INFO   == 20 == 2 == DBG_TRACE
        #   WARNING== 30 ==
        #   ERROR  == 40 == 1 == DBG_ERROR
        #   CRITIC == 50 ==
        #
        val = {
            log.NOTSET: 0,
            log.DEBUG: 4,
            log.INFO: 2,
            log.ERROR: 1,
        }[lvl]

        # Change in the IcePAP library
        self.libdevice.set_verbose(val)

        # Always return the current eMotion level
        self.log_info("log_level(%s) called, lib(%d)" %
                      (log.getLevelName(lvl), val))
        return log.level()

    def log_error(self, msg):
        """Logging method"""
        log.error(_ICEPAP_TAB + msg)

    def log_info(self, msg):
        """Logging method"""
        log.info(_ICEPAP_TAB + msg)


    def set_parameter(self, axis, par_list):
        """Set the trajectory parameter values"""
        self.libtraj[axis].set_parameter(par_list)


    def get_parameter(self, axis):
        """Returns the trajectory parameter values"""
        return self.libtraj[axis].get_parameter()


    def set_trajectory(self, axis, hw_axis, pos_list):
        """
        Set the trajectory position values for a given real axis
        
        The position values are given in user unit
        """

        # convert user units into IcePAP motor steps
        stp_sz   = hw_axis.steps_per_unit
        stp_list = [ x*stp_sz for x in pos_list ] 
        self.libtraj[axis].add_axis_trajectory(hw_axis.libaxis, stp_list)


    def drain(self, axis):
        """Empty any previously defined trajectory"""
        self.libtraj[axis].drain()


    def load(self, axis):
        """Load the full trajectory into the IcePAP system"""
        self.libtraj[axis].load()


    def sync(self, axis, par_val):
        """Put all IcePAP axes on the trajectory"""
        self.libtraj[axis].sync(par_val)
