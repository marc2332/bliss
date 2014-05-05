from bliss.controllers.motor import Controller
from bliss.common.axis import READY, MOVING
from bliss.controllers.motor import add_axis_method
import math
import time

"""
mockup.py : a mockup controller for bliss.
To be used as skeleton to write bliss plugin controller.
"""

def mockup_err(msg):
    log.error("[MOCKUP] " + msg)


def mockup_info(msg):
    log.info("[MOCKUP] " + msg)


def mockup_debug(msg):
    log.debug("[MOCKUP] " + msg)


class Mockup(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self._axis_moves = {}

        # Access to the config.
        self.config.get("host")

        # add a setting name 'init_count' of type 'int'
        self.axis_settings.add('init_count', int)

        # Settings of xml config like "velocity" are automatically added.

    '''
    Controller initialization actions.
    '''

    def initialize(self):
        # hardware initialization
        for axis_name, axis in self.axes.iteritems():
            axis.settings.set('init_count', 0)
            # set initial speed
            axis.settings.set('velocity', axis.config.get("velocity", float))

    '''
    Axes initialization actions.
    '''

    def initialize_axis(self, axis):
        self._axis_moves[axis] = {
            "end_t": 0,
            "end_pos": 30}

        # this is to test axis are initialized only once
        axis.settings.set('init_count', axis.settings.get('init_count') + 1)

        # Add new axis oject method.
        add_axis_method(axis, self.get_identifier)

    '''
    Actions to perform at controller closing.
    '''

    def finalize(self):
        pass

    def start_all(self, *motion_list):
        t0 = time.time()
        for motion in motion_list:
            self.start_one(motion, t0=t0)

    def start_one(self, motion, t0=None):
        axis = motion.axis
        t0 = t0 or time.time()
        pos = self.read_position(axis)
        v = self.read_velocity(axis) * axis.steps_per_unit()
        self._axis_moves[axis] = {
            "start_pos": pos,
            "delta": motion.delta,
            "end_pos": motion.target_pos,
            "end_t": t0 +
            math.fabs(
                motion.delta) /
            float(v),
            "t0": t0}

    '''
    Always return the position (measured or desired) taken from controller
    in steps.
    '''

    def read_position(self, axis, measured=False):
        if measured:
            return -1.2345
        else:
            # Always return position
            if self._axis_moves[axis]["end_t"]:
                # motor is moving
                t = time.time()
                v = self.read_velocity(axis) * axis.steps_per_unit()
                d = math.copysign(1, self._axis_moves[axis]["delta"])
                dt = t - self._axis_moves[axis]["t0"]
                pos = self._axis_moves[axis]["start_pos"] + d * dt * v
                return pos
            else:
                return self._axis_moves[axis]["end_pos"]

    #def set_position(self, axis, new_pos):
    #    self._axis_moves[axis]["end_pos"] = new_pos
    #    self._axis_moves[axis]["end_t"] = 0
    #    return new_pos

    '''
    Always return the current velocity taken from controller
    in steps/sec.
    '''

    def read_velocity(self, axis):
        return float(axis.settings.get('velocity'))

    def set_velocity(self, axis, new_velocity):
        axis.settings.set('velocity', new_velocity)
        return new_velocity

    '''
    Always return the current acceleration time taken from controller
    in seconds.
    '''

    def read_acctime(self, axis):
        return float(axis.settings.get('acctime'))

    def set_acctime(self, axis, new_acctime):
        axis.settings.set('acctime', new_acctime)
        return new_acctime

    '''
    '''

    def state(self, axis):
        if self._axis_moves[axis]["end_t"] > time.time():
            return MOVING
        else:
            self._axis_moves[axis]["end_t"] = 0
            return READY

    '''
    Must send a command to the controller to abort the motion of given axis.
    '''

    def stop(self, axis):
        self._axis_moves[axis]["end_pos"] = self.read_position(axis)
        self._axis_moves[axis]["end_t"] = 0

    def stop_all(self, *motion_list):
        for motion in motion_list:
            axis = motion.axis
            self._axis_moves[axis]["end_pos"] = self.read_position(axis)
            self._axis_moves[axis]["end_t"] = 0

    def home_search(self, axis):
        self._axis_moves[axis]["end_pos"] = 0
        self._axis_moves[axis]["end_t"] = 0
        self._axis_moves[axis]["home_search_start_time"] = time.time()

#    def home_set_hardware_position(self, axis, home_pos):
#        raise NotImplementedError

    def home_state(self, axis):
        return READY if (time.time() - self._axis_moves[axis]["home_search_start_time"]) > 2 else MOVING

    '''
    Custom axis method returning the current name of the axis
    '''

    def get_identifier(self, axis):
        return axis.name
