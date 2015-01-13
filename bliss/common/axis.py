
import bliss
from bliss.common import log as elog
from bliss.common.task_utils import *
from bliss.controllers.motor_settings import AxisSettings
from bliss.common import event
import time
import gevent

READY, MOVING, FAULT, UNKNOWN, OFF = (
    "READY", "MOVING", "FAULT", "UNKNOWN", "OFF")

class Motion(object):

    def __init__(self, axis, target_pos, delta):
        self.__axis = axis
        self.target_pos = target_pos
        self.delta = delta
        self.backlash = 0

    @property
    def axis(self):
        return self.__axis


class Axis(object):

    def __init__(self, name, controller, config):
        self.__name = name
        self.__controller = controller
        from bliss.config.motors import StaticConfig
        self.__config = StaticConfig(config)
        self.__settings = AxisSettings(self) 
        self.__settings.set("offset", 0)
        self.__move_done = gevent.event.Event()
        self.__move_done.set()
        self.__custom_methods_list = list()
        self.__move_task = None
        self.__set_position = None

    @property
    def name(self):
        return self.__name

    @property
    def controller(self):
        return self.__controller

    @property
    def config(self):
        return self.__config

    @property
    def settings(self):
        return self.__settings

    @property
    def is_moving(self):
        return not self.__move_done.is_set()

    @property
    def offset(self):
        return self.__settings.get("offset")

    @property
    def sign(self):
        return self.config.get("sign", int, 1)

    @property
    def steps_per_unit(self):
        return self.config.get("steps_per_unit", float, 1)

    @property
    def encoder_steps_per_unit(self):
        return self.config.get("encoder_steps_per_unit", float, self.steps_per_unit)

    @property
    def custom_methods_list(self):
        # return a copy of the custom methods list
        return self.__custom_methods_list[:]

    def has_tag(self, tag):
        for t, axis_list in self.__controller._tagged.iteritems():
            if t != tag:
                continue
            if self.name in [axis.name for axis in axis_list]:
                return True
        return False

    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))

    def on(self):
        if self.is_moving:
            return

        self.__controller.set_on(self)
        state = self.__controller.state(self)
        self.settings.set("state", state, write=False)

    def off(self):
        if self.is_moving:
            raise RuntimeError("Can't set power off while axis is moving")

        self.__controller.set_off(self)
        state = self.__controller.state(self)
        self.settings.set("state", state, write=False)

    def set_position(self):
        return self.__set_position

    def measured_position(self):
        """
        Returns a value in user units.
        """
        return self.dial2user(self.dial_measured_position())

    def dial_measured_position(self):
        return self.__controller.read_position(self, measured=True) / self.encoder_steps_per_unit

    def dial(self, new_dial=None):
        """
        Returns current dial position, or set new dial if 'new_dial' argument is provided
        """
        if self.is_moving:
            if new_dial is not None:
                raise RuntimeError("Can't set axis position \
                                    while it is moving")
 
        if new_dial is not None:
            user_pos = self.position()

            # Sends a value in motor units to the controller
            # but returns a user-units value.
            try:
                curr_pos = self.__controller.set_position(self, new_dial * self.steps_per_unit) / self.steps_per_unit
            except NotImplementedError:
                try:
                    curr_pos = self.__controller.read_position(self) / self.steps_per_unit
                except NotImplementedError:
                    curr_pos = 0

            # do not change user pos (update offset)
            self._position(user_pos)

            return curr_pos 
        else:
            return self.user2dial(self.position())

    def position(self, new_pos=None):
        """
        new_pos is in user units.
        Returns a value in user units.
        """
        if self.is_moving:
            if new_pos is not None:
                raise RuntimeError("Can't set axis position \
                                    while it is moving")
            pos = self.settings.get("position")
            if pos is None:
                pos = self._position()
                self.settings.set("position", pos)
                self.settings.set("dial_position", self.user2dial(pos))
        else:
            pos = self._position(new_pos)
            if new_pos is not None:
                self.settings.set("position", pos)
                self.settings.set("dial_position", self.user2dial(pos))
        return pos

    def _position(self, new_pos=None):
        """
        new_pos is in user units.
        Returns a value in user units.
        """
        if new_pos is not None:
            self.__set_position = new_pos

            try:
                curr_pos = self.__controller.read_position(self) / self.steps_per_unit
            except NotImplementedError:
                # this controller does not have a 'position'
                # (e.g like some piezo controllers)
                curr_pos = 0
            self.__settings.set("offset", new_pos - self.sign*curr_pos)
            # update limits
            ll, hl = self.limits()
            self.limits(ll+self.offset if ll is not None else ll, hl+self.offset if hl is not None else hl)

            return self.position()
        else:
            try:
                curr_pos = self.__controller.read_position(self) / self.steps_per_unit
            except NotImplementedError:
                curr_pos = 0
            elog.debug("curr_pos=%g" % curr_pos)
            return self.dial2user(curr_pos)

    def state(self):
        if self.is_moving:
            return MOVING
        # really read from hw
        return self.__controller.state(self)

    def get_info(self):
        return self.__controller.get_info(self)

    def raw_write(self, com):
        self.__controller.raw_write(self, com)

    def raw_write_read(self, com):
        return self.__controller.raw_write_read(self, com)

    def velocity(self, new_velocity=None, from_config=False):
        """
        new_velocity is in user units per seconds.
        """
        if from_config:
            return self.config.get("velocity", float)

        if new_velocity is not None:
            # Converts into motor units to change velocity of axis.
            self.__controller.set_velocity(
                self, new_velocity * abs(self.steps_per_unit))
            _user_vel = new_velocity
        else:
            # Returns velocity read from motor axis.
            _user_vel = self.__controller.read_velocity(
                self) / abs(self.steps_per_unit)

        # Stores velocity in user-units
        self.settings.set("velocity", _user_vel)

        return _user_vel

    def acctime(self, new_acctime=None, from_config=False):
        """
        <new_acctime> given in seconds.
        """
        if from_config:
            return self.velocity(from_config=True)/self.acceleration(from_config=True)
        if new_acctime is not None:
            acc = self.velocity() / new_acctime
            self.acceleration(acc)
        return self.velocity() / self.acceleration()

    def acceleration(self, new_acc=None, from_config=False):
        """
        <new_acc> given in user_units/s2.
        """
        if from_config:
            return self.config.get("acceleration", float)
        if new_acc is not None:
            self.__controller.set_acceleration(self, new_acc*abs(self.steps_per_unit))
        _acceleration = self.__controller.read_acceleration(self) / abs(self.steps_per_unit)
        if new_acc is not None:
            self.settings.set("acceleration", _acceleration)
        return _acceleration

    def limits(self, low_limit=None, high_limit=None):
        """
        <low_limit> and <high_limit> given in user units.
        """
        if low_limit is not None:
            self.settings.set("low_limit", low_limit)
        if high_limit is not None:
            self.settings.set("high_limit", high_limit)
        return self.settings.get('low_limit'), self.settings.get('high_limit')

    def _handle_move(self, motion):
        def update_settings():
            pos = self._position()
            self.settings.set("dial_position", self.user2dial(pos))
            self.settings.set("position", pos)

        with cleanup(update_settings):
            while True:
                state = self.__controller.state(self)
                if state != MOVING:
                    break
                update_settings()
                time.sleep(0.02)

            if motion.backlash:
                # axis has moved to target pos - backlash;
                # now do the final motion (backlash) to reach original target.
                elog.debug("doing backlash (%g)" % motion.backlash)
                final_pos = motion.target_pos + motion.backlash
                backlash_motion = Motion(self, final_pos, motion.backlash)
                self.__controller.prepare_move(backlash_motion)
                self.__controller.start_one(backlash_motion)
                self._handle_move(backlash_motion)

    def _handle_sigint(self):
        if self.is_moving:
            self.__move_task.kill(KeyboardInterrupt)

    def dial2user(self, position):
        return (self.sign*position) + self.offset

    def user2dial(self, position):
        return (position - self.offset)/self.sign

    def prepare_move(self, user_target_pos, relative=False):
        if relative:
             user_initial_pos = self.__set_position if self.__set_position is not None else self.position()
             user_target_pos += user_initial_pos
        else:
             user_initial_pos = self.position()
        dial_initial_pos = self.user2dial(user_initial_pos)
        dial_target_pos = self.user2dial(user_target_pos)
        self.__set_position = user_target_pos
        if abs(dial_target_pos - dial_initial_pos) < 1E-6:
            return

        elog.debug("prepare_move : user_initial_pos=%g user_target_pos=%g dial_target_pos=%g dial_intial_pos=%g relative=%s" %
                   (user_initial_pos, user_target_pos, dial_target_pos, dial_initial_pos, relative))

        user_backlash = self.config.get("backlash", float, 0)
        # all positions are converted to controller units
        backlash = user_backlash * self.steps_per_unit
        delta_dial = dial_target_pos - dial_initial_pos
        delta = self.dial2user(delta_dial * self.steps_per_unit)
        target_pos = dial_target_pos * self.steps_per_unit

        if backlash:
            if cmp(delta, 0) != cmp(backlash, 0):
                # move and backlash are not in the same direction;
                # apply backlash correction, the move will happen
                # in 2 steps
                target_pos -= backlash
                delta -= backlash
            else:
                # don't do backlash correction
                backlash = 0

        # check software limits
        user_low_limit, user_high_limit = self.limits()
        if not None in (user_low_limit, user_high_limit):
          high_limit = self.user2dial(user_high_limit) * self.steps_per_unit
          low_limit = self.user2dial(user_low_limit) * self.steps_per_unit 
          if high_limit < low_limit:
              high_limit, low_limit = low_limit, high_limit
        else:
          user_low_limit = None
          user_high_limit = None
        backlash_str = " (with %f backlash)" % user_backlash if backlash else ""
        if user_low_limit is not None:
            if target_pos < low_limit:
                raise ValueError(
                    "Move to `%f'%s would go below low limit (%f)" %
                    (user_target_pos, backlash_str, user_low_limit))
        if user_high_limit is not None:
            if target_pos > high_limit:
                raise ValueError(
                    "Move to `%f' %s would go beyond high limit (%f)" %
                    (user_target_pos, backlash_str, user_high_limit))

        motion = Motion(self, target_pos, delta)
        motion.backlash = backlash

        self.__controller.prepare_move(motion)

        return motion

    def _set_moving_state(self):
        self.__move_done.clear()
        self.settings.set("state", MOVING, write=False)

    def _set_move_done(self, move_task):
        self.__move_done.set()
        event.send(self, "move_done", True)
        self.settings.set("state", self.state(), write=False)
 
        if move_task is not None and not move_task._being_waited:
            try:
                move_task.get()
            except:
                sys.excepthook(*sys.exc_info())

    def _check_ready(self):
        initial_state = self.state()
        if initial_state != READY:
            raise RuntimeError("axis %s state is \
                                %r" % (self.name, initial_state))

    def move(self, user_target_pos, wait=True, relative=False):
        if self.__controller.is_busy():
            raise RuntimeError("axis %s: controller is busy" % self.name)
        self._check_ready()

        motion = self.prepare_move(user_target_pos, relative)

        self._set_moving_state()
        self.__move_task = None

        try:
            event.send(self, "move_done", False)
            self.__move_task = self._do_move(motion, wait=False) 
        except:
            self._set_move_done(None)
            raise
        else:
            self.__move_task._being_waited = wait
            self.__move_task.link(self._set_move_done)

        if wait:
            self.__move_task.get()
        else:
            return self.__move_task

    @task
    def _do_move(self, motion, wait=True):
        if motion is None:
            return
        with error_cleanup(self.stop):
            self.__controller.start_one(motion)

            self._handle_move(motion)

    def rmove(self, user_delta_pos, wait=True):
        return self.move(user_delta_pos, wait, relative=True)

    def wait_move(self):
        self.__move_done.wait()

    def stop(self):
        if self.is_moving:
            self.__controller.stop(self)
            self.__set_position = None
            self.__move_done.set()

    def home(self, home_pos=None, wait=True):
        self._check_ready()

        # flag "must the position to be set ?"
        _set_pos = False

        if home_pos is not None:
            try:
                self.__controller.home_set_hardware_position(
                        self, home_pos)
            except NotImplementedError:
                _set_pos = True

        self._set_moving_state()

        home_task = self._do_home(wait=False)
        home_task._being_waited = wait
        home_task.link(self._set_move_done)
        if _set_pos:
            # it is not possible to change position
            # while axis has a moving state,
            # so we register a callback to be executed
            # *after* _set_move_done.
            def set_pos(g, home_pos=home_pos):
                self.dial(home_pos)
                self.position(home_pos)
            home_task.link(set_pos)

        if wait:
            home_task.get()
        else:
            return home_task

    @task
    def _do_home(self):
        with error_cleanup(self.stop):
            self.__controller.home_search(self)
            while True:
                state = self.__controller.home_state(self)
                if state != MOVING:
                    break
                time.sleep(0.02)

    def hw_limit(self, limit, lim_pos=None, wait=True):
        """Go to a hardware limit

        Parameters:
            limit   - integer, positive means "positive limit"
            lim_pos - if not None, set position to lim_pos once limit is reached
            wait    - boolean, wait for completion (default is to wait)
        """
        limit = int(limit)
        self._check_ready()
        _set_pos = False
        if lim_pos is not None:
          lim_pos = float(lim_pos)
          _set_pos = True

        self._set_moving_state()

        lim_search_task = self._do_limit_search(limit, wait=False)
        lim_search_task._being_waited = wait
        lim_search_task.link(self._set_move_done)
        if _set_pos:
            def set_pos(g, lim_pos=lim_pos):
                self.dial(lim_pos)
                self.position(lim_pos) 
            lim_search_task.link(set_pos)

        if wait:
            lim_search_task.get()
        else:
            return lim_search_task

    @task
    def _do_limit_search(self, limit):
        with error_cleanup(self.stop):
            self.__controller.limit_search(self, limit)
            while True:
                state = self.__controller.state(self)
                if state != MOVING:
                    break
                time.sleep(0.02)


class AxisRef(object):

    def __init__(self, name, _, config):
        self.__name = name
        self.__config = config
        self.settings = AxisSettings(None)

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config
