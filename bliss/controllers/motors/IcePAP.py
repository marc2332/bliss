"""
Bliss generic library
"""
from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING, UNKNOWN


"""
IcePAP specific library
"""
import icepap.lib


"""
Extra modules
"""
#import pdb

"""
Global resources
"""
_ICEPAP_TAB = "IcePAP: "


class IcePAP(Controller):

    """Implement IcePAP stepper motor controller access"""

    def __init__(self, name, config, axes):
        """Contructor"""
        Controller.__init__(self, name, config, axes)

    def initialize(self):
        """Controller initialization"""
        self.log_info("initialize() called")

        # Get controller config from bliss config
        # Mandatory parameters
        self.host = self.config.get("host")

        # Optional parameters
        try:
            self.libdebug = int(self.config.get("libdebug"))
        except:
            self.libdebug = 1

        # Create an IcePAP lib object to access the MASTER
        self.libdevice = icepap.lib.System(
            self.host,
            "verb=%d" %
            self.libdebug)

        # Create an IcePAP lib object as default group
        self.libgroup = icepap.lib.Group("default")

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
        self.libdevice.close()

    def initialize_axis(self, axis):
        """Axis initialization"""
        self.log_info("initialize_axis() called for axis \"%s\"" % axis.name)

        # Get axis config from bliss config
        axis.address = axis.config.get("address", int)

        # Create an IcePAP lib axis object
        device = self.libdevice
        address = axis.address
        name = axis.name
        axis.libaxis = icepap.lib.Axis(device, address, name)

        # Add the axis to the default IcePAP lib group
        self.libgroup.add_axis(axis.libaxis)

        # Initialiaze hardware
        self.libgroup.set_power(icepap.lib.ON, axis.libaxis)

        # Add new axis oject methods
        add_axis_method(axis, self.get_identifier)

    def read_position(self, axis, measured=False):
        """Returns axis position in motor units"""
        self.log_info("position() called for axis \"%s\"" % axis.name)
        return self.libgroup.pos(axis.libaxis)

    def set_position(self, axis, new_pos):
        l = icepap.lib.PosList()
        l[axis.libaxis] = new_pos
        self.libgroup.pos(l)
        return self.read_position(axis)

    def read_velocity(self, axis):
        """Returns axis current velocity in user units per seconds"""
#         ??? ca serai pas mieux en motor units ? (steps/s)
        return self.libgroup.velocity(axis.libaxis)

    def set_velocity(self, axis, new_velocity):
        s = "%f" % new_velocity
        self.log_info("set_velocity(%s) called for axis \"%s\"" %
                      (s, axis.name))

        l = icepap.lib.VelList()
        l[axis.libaxis] = new_velocity
        self.libgroup.velocity(l)

        # Always return the current velocity
        return self.read_velocity(axis)

    def read_acctime(self, axis):
        """Returns axis current acceleratin time in seconds"""
        return self.libgroup.acctime(axis.libaxis)

    def set_acctime(self, axis, new_acctime):
        s = "%f" % new_acctime
        self.log_info("set_acctime(%s) called for axis \"%s\"" %
                      (s, axis.name))

        l = icepap.lib.AcctimeList()
        l[axis.libaxis] = new_acctime
        self.libgroup.acctime(l)

        return self.read_acctime(axis)

    def state(self, axis):
        """Returns the current axis state"""
        self.log_info("state() called for axis \"%s\"" % axis.name)

        # The axis can only be accessed through a group in IcePAP lib
        # Use the default group
        status = self.libgroup.status(axis.libaxis)

        # Convert status formats
        if(icepap.lib.status_ismoving(status)):
            return MOVING
        if(icepap.lib.status_isready(status)):
            return READY

        # Abnormal end
        return UNKNOWN

    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        self.log_info("prepare_move() called for axis \"%s\"" %
                      motion.axis.name)
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        self.log_info("start_one() called for axis \"%s\"" % motion.axis.name)
        target_positions = icepap.lib.PosList()
        target_positions[motion.axis.libaxis] = motion.target_pos
        self.libgroup.move(target_positions)

    def start_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately,
        positions in motor units
        """
        self.log_info("start_all() called")
        target_positions = icepap.lib.PosList()
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
