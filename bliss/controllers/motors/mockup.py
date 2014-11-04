from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import READY, MOVING, OFF
from bliss.controllers.motor import add_axis_method
import math
import time
import random

"""
mockup.py : a mockup controller for bliss.
To be used as skeleton to write bliss plugin controller.
"""

"""
config :
 'velocity' in unit/s
 'acctime' in s
 'steps_per_unit' in unit^-1  (default 1)
 'backlash' in unit
"""

config_xml = """
<config>
  <controller class="mockup">
    <axis name="robx" class="MockupAxis">
      <velocity  value="1"/>
      <acctime value="0.333"/>
      <steps_per_unit value="10"/>
      <backlash value="2"/>
    </axis>
  </controller>
</config>
"""


class Mockup(Controller):
    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self._axis_moves = {}

        # Access to the config.
        try:
            self.config.get("host")
        except:
            elog.debug("no 'host' defined in config for %s" % name)

        # Adds a Mockup specific setting named 'init_count' of type 'int'
        self.axis_settings.add('init_count', int)

    """
    Controller initialization actions.
    """
    def initialize(self):
        # hardware initialization
        for axis_name, axis in self.axes.iteritems():
            axis.settings.set('init_count', 0)
            # set initial speed
            axis.settings.set('velocity', axis.config.get("velocity", float))

    """
    Axes initialization actions.
    """
    def initialize_axis(self, axis):
        self._axis_moves[axis] = {
            "measured_simul": False,
            "measured_noise": 0.0,
            "end_t": 0,
            "end_pos": 30}

        # this is to test axis are initialized only once
        axis.settings.set('init_count', axis.settings.get('init_count') + 1)

        # Add new axis oject method.
        add_axis_method(axis, self.custom_park, types_info=(None, None))
        add_axis_method(axis, self.custom_get_forty_two, types_info=(None, int))
        add_axis_method(axis, self.custom_get_twice, types_info=(int, int))
        add_axis_method(axis, self.custom_get_chapi, types_info=(str, str))
        add_axis_method(axis, self.custom_send_command, types_info=(str, None))
        add_axis_method(axis, self.custom_command_no_types)
        add_axis_method(axis, self.custom_simulate_measured, types_info=(bool, None))
        add_axis_method(axis, self.custom_set_measured_noise, types_info=(float, None))

    """
    Actions to perform at controller closing.
    """
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
        v = self.read_velocity(axis)
        self._axis_moves[axis].update( {
            "start_pos": pos,
            "delta": motion.delta,
            "end_pos": motion.target_pos,
            "end_t": t0 +
            math.fabs(
                motion.delta) /
            float(v),
            "t0": t0})

    def read_position(self, axis, measured=False):
        """
        Returns the position (measured or desired) taken from controller
        in controller unit (steps).
        """

        # handle rough simulated position for unit tests mainly
        if measured and self._axis_moves[axis]["measured_simul"]:
            return int(round(-1.2345 * axis.steps_per_unit))

        # handle read out during a motion
        if self._axis_moves[axis]["end_t"]:
            # motor is moving
            t = time.time()
            v = self.read_velocity(axis)
            d = math.copysign(1, self._axis_moves[axis]["delta"])
            dt = t - self._axis_moves[axis]["t0"]
            pos = self._axis_moves[axis]["start_pos"] + d * dt * v
        else:
            pos = self._axis_moves[axis]["end_pos"]

        # simulate noisy encoder
        if measured and (self._axis_moves[axis]["measured_noise"] != 0.0):
            noise_mm = random.uniform(
                -self._axis_moves[axis]["measured_noise"],
                self._axis_moves[axis]["measured_noise"])
            noise_stps = noise_mm * axis.steps_per_unit
            pos += noise_stps

        # always return position
        return int(round(pos))

    def read_velocity(self, axis):
        """
        Returns the current velocity taken from controller
        in motor units.
        """
        _user_velocity = axis.settings.get('velocity')
        _mot_velocity = _user_velocity * abs(axis.steps_per_unit)
        return float(_mot_velocity)

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        Returns velocity in motor units.
        """
        _user_velocity = new_velocity / abs(axis.steps_per_unit)
        axis.settings.set('velocity', _user_velocity)

        return new_velocity

    """
    Always return the current acceleration time taken from controller
    in seconds.
    """

    def read_acctime(self, axis):
        _acctime = float(axis.settings.get('acctime'))

        elog.debug("readd acctime : %g" % _acctime)
        return _acctime

    def set_acctime(self, axis, new_acctime):
        axis.settings.set('acctime', new_acctime)
        return new_acctime

    def read_acceleration(self, axis):
        _acctime = float(axis.settings.get('acctime'))
        _velocity = float(axis.settings.get('velocity'))
        _acceleration = _velocity / _acctime
        return _acceleration

    def set_acceleration(self, axis, new_acceleration):
        axis.settings.set('acceleration', new_acceleration)
        return new_acceleration

    def set_on(self, axis):
        self._axis_moves[axis]["on"] = True

    def set_off(self, axis):
        self._axis_moves[axis]["on"] = False

    """
    """

    def state(self, axis):
        if not self._axis_moves[axis].get("on", True):
            return OFF
        if self._axis_moves[axis]["end_t"] > time.time():
            return MOVING
        else:
            self._axis_moves[axis]["end_t"] = 0
            return READY

    """
    Must send a command to the controller to abort the motion of given axis.
    """
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
        return READY if(time.time() - self._axis_moves[axis]
                        ["home_search_start_time"]) > 2 else MOVING

    def get_info(self, axis):
        return "turlututu chapo pointu : %s" % axis.name

    def raw_write(self, axis, com):
        print ("raw_write:  com = %s" % com)

    def raw_write_read(self, axis, com):
        return com + ">-<" + com

    def set_position(self, axis, pos):
        self._axis_moves[axis]["end_pos"]=pos
        self._axis_moves[axis]["end_t"] = 0
        return pos

    """
    Custom axis method returning the current name of the axis
    """
    # VOID VOID
    def custom_park(self, axis):
        print "parking"

    # VOID LONG
    def custom_get_forty_two(self, axis):
        return 42

    # LONG LONG
    def custom_get_twice(self, axis, LongValue):
        return LongValue * 2

    # STRING STRING
    def custom_get_chapi(self, axis, value):
        if value == "chapi":
            return "chapo"
        elif value == "titi":
            return "toto"
        else:
            return "bla"

    # STRING VOID
    def custom_send_command(self, axis, value):
        print "command=", value

    def custom_command_no_types(self, axis):
        print "print with no types"

    def custom_simulate_measured(self, axis, flag):
        """
        Custom axis method to emulated measured position
        """
        if type(flag) != bool:
            raise ValueError('argin must be boolean')
        self._axis_moves[axis]["measured_simul"] = flag

    def custom_set_measured_noise(self, axis, noise):
        """
        Custom axis method to add a random noise, given in user units,
        to measured positions. Set noise value to 0 to have a measured
        position equal to target position.
        """
        self._axis_moves[axis]["measured_noise"] = noise
