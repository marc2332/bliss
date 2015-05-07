
import types
import functools
from bliss.controllers.motor_settings import ControllerAxisSettings
from bliss.common.axis import AxisRef
from bliss.controllers.motor_group import Group
from bliss.config.motors import get_axis
from bliss.common import event


def add_axis_method(axis_object, method, name=None, args=[], types_info=(None, None)):

    if name is None:
        name = method.im_func.func_name

    def call(self, *args, **kwargs):
        return method.im_func(method.im_self, *args, **kwargs)

    axis_object._add_custom_method(
        types.MethodType(functools.partial(call, *([axis_object] + args)),
                         axis_object), name, types_info)


class Controller(object):

    def __init__(self, name, config, axes, encoders):
        self.__name = name
        from bliss.config.motors import StaticConfig
        self.__config = StaticConfig(config)
        self.__initialized_axis = dict()
        self._axes = dict()
        self._encoders = dict()
        self.__initialized_encoder = dict()
        self._tagged = dict()

        self.axis_settings = ControllerAxisSettings()

        for axis_name, axis_class, axis_config in axes:
            axis = axis_class(axis_name, self, axis_config)
            self._axes[axis_name] = axis
            axis_tags = axis_config.get('tags')
            if axis_tags:
                for tag in axis_tags.split():
                    self._tagged.setdefault(tag, []).append(axis)  # _name)
            self.__initialized_axis[axis] = False
        for encoder_name, encoder_class, encoder_config in encoders:
            encoder = encoder_class(encoder_name, self, encoder_config)
            self._encoders[encoder_name] = encoder
            self.__initialized_encoder[encoder] = False


    @property
    def axes(self):
        return self._axes

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    def _update_refs(self):
        for tag, axis_list in self._tagged.iteritems():
            for i, axis in enumerate(axis_list):
                if not isinstance(axis, AxisRef):
                    continue
                referenced_axis = get_axis(axis.name)
                self.axes[axis.name] = referenced_axis
                axis_list[i] = referenced_axis
                referenced_axis.controller._tagged.setdefault(tag, []).append(referenced_axis)
        """
            referenced_axis = get_axis(axis.name)
            self.axes[axis.name] = referenced_axis
            self.__initialized_axis[referenced_axis] = True
            for tag, axis_list in self._tagged.iteritems():
                try:
                    i = axis_list.index(axis)
                except ValueError:
                    continue
                else:
                    axis_list[i] = referenced_axis
                    referenced_axis.controller._tagged.setdefault(
                        tag,
                        []).append(referenced_axis)
        """

    def initialize(self):
        pass

    def __del__(self):
        self.finalize()

    def finalize(self):
        pass

    def get_axis(self, axis_name):
        axis = self._axes[axis_name]

        if not self.__initialized_axis[axis]:
            # load settings
            axis.settings.load_from_config()

            self.initialize_axis(axis)
            self.__initialized_axis[axis] = True

            # apply settings or config parameters
            def get_setting_or_config_value(name, converter=float):
                value = axis.settings.get(name)
                if value is None:
                    try:
                        value = axis.config.get(name, converter)
                    except:
                        # print "no config value for %s " % name
                        return None
                return value

            mandatory_config_list = list()

            for config_param in ['velocity', 'acceleration']:
                # Try to execute read_<config_name> to check if controller support it.
                reading_function = getattr(axis.controller, "read_%s" % config_param)
                try:
                    reading_function(axis)
                except NotImplementedError:
                    #print "<config_param> seems not supported by your controller."
                    #print "  no [read|set]_<config_param> method."
                    print "%s not implemented in your controller." % config_param
                    pass
                else:
                    mandatory_config_list.append(config_param)

            for setting_name in mandatory_config_list:
                value = get_setting_or_config_value(setting_name)
                if value is None:
                    raise RuntimeError("%s is missing in configuration." % setting_name)
                meth = getattr(axis, setting_name)
                meth(value)

            low_limit = get_setting_or_config_value("low_limit")
            high_limit = get_setting_or_config_value("high_limit")
            axis.limits(low_limit, high_limit)

        return axis

    def initialize_axis(self, axis):
        raise NotImplementedError

    def get_encoder(self, encoder_name):
        encoder = self._encoders[encoder_name]

        if not self.__initialized_encoder[encoder]:
            self.initialize_encoder(encoder)
            self.__initialized_encoder[encoder] = True

        return encoder

    def initialize_encoder(self, encoder):
        raise NotImplementedError

    def is_busy(self):
        return False

    def prepare_move(self, motion):
        return

    def start_one(self, motion):
        raise NotImplementedError

    def start_all(self, *motion_list):
        raise NotImplementedError

    def stop(self, axis):
        raise NotImplementedError

    def stop_all(self):
        raise NotImplementedError

    def state(self, axis):
        raise NotImplementedError

    def get_info(self, axis):
        raise NotImplementedError

    def raw_write(self, axis, com):
        raise NotImplementedError

    def raw_write_read(self, axis, com):
        raise NotImplementedError

    def home_search(self, axis):
        raise NotImplementedError

    def home_set_hardware_position(self, axis, home_pos):
        raise NotImplementedError

    def home_state(self, axis):
        raise NotImplementedError

    def limit_search(self, axis, limit):
        raise NotImplementedError

    def read_position(self, axis):
        raise NotImplementedError

    def set_position(self, axis, new_position):
        raise NotImplementedError

    def read_encoder(self, encoder):
        raise NotImplementedError

    def set_encoder(self, encoder, new_value):
        raise NotImplementedError
  
    def read_velocity(self, axis):
        raise NotImplementedError

    def set_velocity(self, axis, new_velocity):
        raise NotImplementedError

    def set_on(self, axis):
        raise NotImplementedError

    def set_off(self, axis):
        raise NotImplementedError

    def read_acceleration(self, axis):
        raise NotImplementedError

    def set_acceleration(self, axis, new_acc):
        raise NotImplementedError


class CalcController(Controller):

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._reals_group = None

    def initialize(self):
        for axis in self.pseudos:
            self.get_axis(axis.name)

    def _update_refs(self):
        Controller._update_refs(self)

        self.reals = []
        for real_axis in self._tagged['real']:
            # check if real axis is really from another controller
            if real_axis.controller == self:
                raise RuntimeError(
                    "Real axis '%s` doesn't exist" % real_axis.name)
            self.reals.append(real_axis)
            event.connect(real_axis, 'position', self._calc_from_real)
            event.connect(real_axis, 'state', self._update_state_from_real)
            event.connect(real_axis, "move_done", self._real_move_done)
        self._reals_group = Group(*self.reals)
        self.pseudos = [
            axis for axis_name,
            axis in self.axes.iteritems() if axis not in self.reals]

    def _calc_from_real(self, *args, **kwargs):
        real_positions_by_axis = self._reals_group.position()
        real_positions = dict()

        for tag, axis_list in self._tagged.iteritems():
            if len(axis_list) > 1:
                continue
            axis = axis_list[0]

            if axis in self.reals:
                real_positions[tag] = real_positions_by_axis[axis]

        new_positions = self.calc_from_real(real_positions)

        for tagged_axis_name, position in new_positions.iteritems():
            axis = self._tagged[tagged_axis_name][0]
            if axis in self.pseudos:
                axis.settings.set("dial_position", position)
                axis.settings.set("position", axis.dial2user(position))
            else:
                raise RuntimeError("cannot assign position to real motor")

    def calc_from_real(self, real_positions):
        """Return a dict { pseudo motor tag: new position, ... }"""
        raise NotImplementedError

    def _update_state_from_real(self, *args, **kwargs):
        state = self._reals_group.state()
        for axis in self.pseudos:
            axis.settings.set("state", state, write=False)

    def _real_move_done(self, done):
        if done:
            for axis in self.pseudos:
                if axis.encoder:
                    # check position and raise RuntimeError if encoder
                    # position doesn't correspond to axis position
                    # (MAXE_E)
                    axis._do_encoder_reading()

    def initialize_axis(self, axis):
        if axis in self.pseudos:
            self._calc_from_real()
            self._update_state_from_real()

    def start_one(self, motion):
        positions_dict = dict()
        axis_tag = None
        for tag, axis_list in self._tagged.iteritems():
            if len(axis_list) > 1:
                continue
            x = axis_list[0]
            if x in self.pseudos:
                if x == motion.axis:
                    axis_tag = tag
                    positions_dict[tag] = motion.target_pos
                else:
                    positions_dict[tag] = x.position()

        move_dict = dict()
        for axis_tag, target_pos in self.calc_to_real(axis_tag, positions_dict).iteritems():
            real_axis = self._tagged[axis_tag][0]
            move_dict[real_axis] = target_pos
        self._reals_group.move(move_dict, wait=False)

    def calc_to_real(self, axis_tag, positions_dict):
        raise NotImplementedError

    def stop(self, axis):
        self._reals_group.stop()

    def read_position(self, axis):
        return axis.settings.get("dial_position")

    def state(self, axis, new_state=None):
        return self._reals_group.state()

    def read_velocity(self, axis):
        # no better idea...
        return 0

    def set_velocity(self, axis, new_velocity):
        return new_velocity
