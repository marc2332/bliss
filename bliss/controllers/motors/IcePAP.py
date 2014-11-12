import sys
import os

"""
Bliss generic library
"""
from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING, UNKNOWN

"""
Extra modules
"""
#import pdb
#from icepap_utils import lib 
import libicepap

"""
Global resources
"""
_ICEPAP_TAB = "IcePAP: "


class IcePAP(Controller):

    """Implement IcePAP stepper motor controller access"""
    default_group = None

    def __init__(self, name, config, axes):
        """Contructor"""
        Controller.__init__(self, name, config, axes)

        self.libdevice = None

    def initialize(self):
        """Controller initialization"""
        self.log_info("initialize() called")

        # Get controller config from bliss config
        # Mandatory parameters (port number is not needed)
        self.host = self.config.get("host")

        # Optional parameters
        try:
            self.libdebug = int(self.config.get("libdebug"))
        except:
            self.libdebug = 1

        # Create an IcePAP lib object to access the MASTER
        self.libdevice = libicepap.System(
            self.host,
            "verb=%d" %
            self.libdebug)

        # Create an IcePAP lib object as default group
        if IcePAP.default_group is None:
            IcePAP.default_group = libicepap.Group("default")
        self.libgroup = IcePAP.default_group


    def finalize(self):
        """Controller no more needed"""
        self.log_info("finalize() called")
        #import pdb;pdb.set_trace()
        # Remove any group in the IcePAP lib
        try:
            self.libgroup.delete()
        except:
            pass

        # Close IcePAP lib socket/threads
        if self.libdevice is not None:
            self.libdevice.close()
        

    def initialize_axis(self, axis):
        """Axis initialization"""
        self.log_info("initialize_axis() called for axis \"%s\"" % axis.name)

        # Get axis config from bliss config
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        axis.address = axis.config.get("address", int)

        # Create an IcePAP lib axis object
        device = self.libdevice
        address = axis.address
        name = axis.name
        axis.libaxis = libicepap.Axis(device, address, name)

        # Add the axis to the default IcePAP lib group
        self.libgroup.add_axis(axis.libaxis)

        # Initialiaze hardware
        # if set_power fails, display exception but let axis
        # be created properly
        try:
            self.libgroup.set_power(libicepap.ON, axis.libaxis)
        except:
            sys.excepthook(*sys.exc_info())

        # Add new axis oject methods
        add_axis_method(axis, self.get_identifier)

    def read_position(self, axis, measured=False):
        """Returns axis position in motor units"""
        self.log_info("position() called for axis \"%s\"" % axis.name)
        return self.libgroup.pos(axis.libaxis)

    def set_position(self, axis, new_pos):
        l = libicepap.PosList()
        l[axis.libaxis] = new_pos
        self.libgroup.pos(l)
        return self.read_position(axis)

    def read_velocity(self, axis):
        """Returns axis current velocity in user units/sec"""
        #TODO: wouldn't be better in steps/s ?
        return self.libgroup.velocity(axis.libaxis)

    def set_velocity(self, axis, new_velocity):
        """Set axis velocity given in units/sec"""
        s = "%f" % new_velocity
        self.log_info("set_velocity(%s) called for axis \"%s\"" %
                      (s, axis.name))

        l = libicepap.VelList()
        l[axis.libaxis] = new_velocity
        self.libgroup.velocity(l)

        # Always return the current velocity
        return self.read_velocity(axis)

    def read_acceleration(self, axis):
        """Returns axis current acceleration in steps/sec2"""
        acctime  = self.libgroup.acctime(axis.libaxis)
        velocity = self.read_velocity(axis)
        return velocity/acctime

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in steps/sec2"""
        s = "%f" % new_acc
        self.log_info("set_acceleration(%s) called for axis \"%s\"" %
                      (s, axis.name))

        velocity     = self.read_velocity(axis)
        new_acctime  = velocity/new_acc
        s = "%f" % new_acctime
        self.log_info("set_acctime(%s) called for axis \"%s\"" %
                      (s, axis.name))

        l = libicepap.AcctimeList()
        l[axis.libaxis] = new_acctime
        self.libgroup.acctime(l)

        return self.read_acceleration(axis)

    def state(self, axis):
        """Returns the current axis state"""
        self.log_info("state() called for axis \"%s\"" % axis.name)

        # The axis can only be accessed through a group in IcePAP lib
        # Use the default group
        status = self.libgroup.status(axis.libaxis)

        # Convert status formats
        if(libicepap.status_ismoving(status)):
            return MOVING
        if(libicepap.status_isready(status)):
            return READY

        # Abnormal end
        return UNKNOWN

    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        self.log_info("prepare_move() called for axis %r: moving to %f (controller unit)" %
                      (motion.axis.name, motion.target_pos))
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        self.log_info("start_one() called for axis \"%s\"" % motion.axis.name)
        target_positions = libicepap.PosList()
        target_positions[motion.axis.libaxis] = motion.target_pos
        self.libgroup.move(target_positions)

    def start_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately,
        positions in motor units
        """
        self.log_info("start_all() called")
        target_positions = libicepap.PosList()
        for motion in motion_list:
            target_positions[motion.axis.libaxis] = motion.target_pos
        self.libgroup.move(target_positions)

    def stop(self, axis):
        """Stops smoothly an axis motion"""
        self.log_info("stop() called for axis \"%s\"" % axis.name)
        self.libgroup.stop(axis.libaxis)

    def stop_all(self, *motion_list):
        """Stops smoothly all the moving axis given"""
        self.log_info("stop_all() called")
        axis_list = []
        for motion in motion_list:
            axis_list.append(motion.axis.libaxis)
        self.libgroup.stop(axis_list)

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

    def get_identifier(self, axis):
        """Returns the unique string identifier of the specified axis"""
        self.log_info("get_identifier() called for axis \"%s\"" % axis.name)
        return self.libgroup.command("?ID", axis.libaxis)
