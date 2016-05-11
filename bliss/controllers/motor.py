
import types
import inspect
import functools
from bliss.controllers.motor_settings import ControllerAxisSettings
from bliss.common.axis import AxisRef
from bliss.controllers.motor_group import Group
from bliss.config.motors import get_axis
from bliss.common import event

# make the link between encoder and axis, if axis uses an encoder
# (only 1 encoder per axis of course)
ENCODER_AXIS = dict()

def add_axis_method(axis_object, method, name=None, args=[], types_info=(None, None)):

    if name is None:
        name = method.im_func.func_name

    def call(self, *args, **kwargs):
        self.__class__.lazy_init(self)
        return method.im_func(method.im_self, *args, **kwargs)

    axis_object._add_custom_method(
        types.MethodType(functools.partial(call, *([axis_object] + args)),
                         axis_object), name, types_info)


def axis_method(method=None, name=None, args=[], types_info=(None, None)):
    """
    The same as add_axis_method but its purpose is to be used as a
    decorator to the controller method which is to be exported as axis method.

    Less flexible than add_axis_method. It will add the same method to **all**
    axes of the controller. But this is the common use case.

    Example::

        from bliss.controllers.motor import Controller, axis_method

        class MyController(Controller):

            @axis_method
            def park(self, axis):
                print('I am parking {0}'.format(axis.name))

            @axis_method(name='info', types_info=(None, 'str'))
            def get_info(self, axis):
                return 'I am MyController::{0}'.format(axis.name)

    """
    if method is None:
        return functools.partial(axis_method, name=name, args=args,
                                 types_info=types_info)

    method._axis_method_ = dict(name=name, args=args, types_info=types_info)

    return method


def add_axis_attribute(axis_object, fget=None, fset=None, name=None,
                       type_info=None):

    if not (fget or fset):
        head = 'add_axis_attribute: %s' % name
        raise ValueError('%s: must have a getter and/or a setter' % head)

    if name is None:
        if fget:
            name = fget.__name__.lstrip('get').lstrip('_')
        else:
            name = fset.__name__.lstrip('set').lstrip('_')

    get_method, set_method = None, None

    if fget:
        def call_get(self, *args, **kwargs):
            self.__class__.lazy_init(self)
            return fget.im_func(fget.im_self, *args, **kwargs)

        get_method = types.MethodType(functools.partial(call_get, axis_object),
                                      axis_object)

    if fset:
        def call_set(self, *args, **kwargs):
            self.__class__.lazy_init(self)
            return fset.im_func(fset.im_self, *args, **kwargs)
        set_method = types.MethodType(functools.partial(call_set, axis_object),
                                      axis_object)

    axis_object._add_custom_attribute(get_method, set_method, name, type_info)



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

        for encoder_name, encoder_class, encoder_config in encoders:
            encoder = encoder_class(encoder_name, self, encoder_config)
            self._encoders[encoder_name] = encoder
            self.__initialized_encoder[encoder] = False
        for axis_name, axis_class, axis_config in axes:
            axis = axis_class(axis_name, self, axis_config)
            self._axes[axis_name] = axis
            axis_tags = axis_config.get('tags')
            if axis_tags:
                for tag in axis_tags.split():
                    self._tagged.setdefault(tag, []).append(axis) 
            self.__initialized_axis[axis] = False
            if axis_config.get("encoder"):
                 encoder_name = axis_config.get("encoder")['value']
                 ENCODER_AXIS[encoder_name] = axis_name

    @property
    def axes(self):
        return self._axes

    @property
    def encoders(self):
        return self._encoders

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

    def initialize(self):
        pass

    def __del__(self):
        self.finalize()

    def finalize(self):
        pass

    def _initialize_axis(self, axis):
        if self.__initialized_axis[axis]:
            return

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
            # Try to see if controller supports setting the <config_param> by
            # checking if it oveloads default set_<config_name> method
            set_name = "set_%s" % config_param
            base_set_method = getattr(Controller, set_name)
            set_method = getattr(axis.controller.__class__, set_name)
            if base_set_method != set_method:
                mandatory_config_list.append(config_param)

        for setting_name in mandatory_config_list:
            value = get_setting_or_config_value(setting_name)
            if value is None:
                raise RuntimeError("%s is missing in configuration for axis '%s`." % (setting_name, axis.name))
            meth = getattr(axis, setting_name)
            meth(value)

        low_limit = get_setting_or_config_value("low_limit")
        high_limit = get_setting_or_config_value("high_limit")
        axis.limits(low_limit, high_limit)

        for member in inspect.getmembers(self):
            name, member = member
            try:
                add_axis_method(axis, member, **member._axis_method_)
            except AttributeError:
                pass


    def get_axis(self, axis_name):
        axis = self._axes[axis_name]

        return axis


    def initialize_axis(self, axis):
        raise NotImplementedError


    def finalize_axis(self, axis):
        raise NotImplementedError


    def get_encoder(self, encoder_name):
        encoder = self._encoders[encoder_name]

        return encoder


    def get_class_name(self):
        return self.__class__.__name__


    def _initialize_encoder(self, encoder):
        if self.__initialized_encoder[encoder]:
            return
       
        if ENCODER_AXIS.get(encoder.name):
            axis_name = ENCODER_AXIS[encoder.name]
            axis = get_axis(axis_name)
            axis.controller._initialize_axis(axis)
 
        self.initialize_encoder(encoder)
        self.__initialized_encoder[encoder] = True


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

    def stop_all(self, *motions):
        raise NotImplementedError

    def state(self, axis):
        raise NotImplementedError

    def get_info(self, axis):
        raise NotImplementedError

    def raw_write(self, com):
        raise NotImplementedError

    def raw_write_read(self, com):
        raise NotImplementedError

    def home_search(self, axis, switch):
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
        """
        Returns the encoder value in *encoder steps*.
        """
        raise NotImplementedError

    def set_encoder(self, encoder, new_value):
        """
        Sets encoder value. <new_value> is in encoder steps.
        """
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
        self._write_settings = False
        self._motion_control = False

    def initialize(self):
        for axis in self.pseudos:
            self._initialize_axis(axis)

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
        self._reals_group = Group(*self.reals)
        event.connect(self._reals_group, 'move_done', self._real_move_done)
        self.pseudos = [axis for axis_name, axis in self.axes.iteritems()
                        if axis not in self.reals]
        for pseudo_axis in self.pseudos:
            event.connect(pseudo_axis, 'sync_hard', self._pseudo_sync_hard)

    def _pseudo_sync_hard(self):
        for real_axis in self.reals:
            real_axis.sync_hard()

    def _axis_tag(self, axis):
        return [tag for tag, axes in self._tagged.iteritems()
                if tag != 'real' and len(axes) == 1 and axis in axes][0]

    def _updated_from_channel(self, setting_name):
        #print [axis.settings.get_from_channel(setting_name) for axis in self.reals]
        return any([axis.settings.get_from_channel(setting_name) for axis in self.reals])

    def _get_set_positions(self):
        def axis_position(x):
            return x.user2dial(x._set_position()) * x.steps_per_unit

        return dict([(self._axis_tag(axis), axis_position(axis))
                     for axis in self.pseudos])

    def _do_calc_from_real(self):
        real_positions_by_axis = self._reals_group.position()
        real_positions = dict([(self._axis_tag(axis), pos)
                               for axis, pos in real_positions_by_axis.items()])
        return self.calc_from_real(real_positions)

    def _calc_from_real(self, *args, **kwargs):
        new_positions = self._do_calc_from_real()

        for tagged_axis_name, position in new_positions.iteritems():
            axis = self._tagged[tagged_axis_name][0]
            if axis in self.pseudos:
                dial_pos = position / axis.steps_per_unit
                user_pos = axis.dial2user(dial_pos)
                if self._write_settings and not self._motion_control:
                    axis.settings.set("_set_position", user_pos, write=True)
                axis.settings.set("dial_position", dial_pos,
                                  write=self._write_settings)
                axis.settings.set("position", user_pos, write=False)
            else:
                raise RuntimeError("cannot assign position to real motor")

    def calc_from_real(self, real_positions):
        """Return a dict { pseudo motor tag: new position, ... }"""
        raise NotImplementedError

    def _update_state_from_real(self, *args, **kwargs):
        self._write_settings = not self._updated_from_channel('state')
        state = self._reals_group.state()
        for axis in self.pseudos:
            #print '_update_state_from_real', axis.name, str(state)
            axis.settings.set("state", state, write=self._write_settings)

    def _real_move_done(self, done):
        if done:
            #print 'MOVE DONE'
            self._motion_control = False
            self._write_settings = False
            for axis in self.pseudos:
                if axis.encoder:
                    # check position and raise RuntimeError if encoder
                    # position doesn't correspond to axis position
                    # (MAXE_E)
                    axis._do_encoder_reading()

    def _initialize_axis(self, axis):
        for axis in self.reals:
            axis.controller._initialize_axis(axis)
        for axis in self.pseudos:
            Controller._initialize_axis(self, axis)

    def initialize_axis(self, axis):
        if axis in self.pseudos:
            self._calc_from_real()
            self._update_state_from_real()

    def start_one(self, motion):
        self.start_all(motion)

    def start_all(self, *motion_list):
        positions_dict = self._get_set_positions()

        move_dict = dict()
        for tag, target_pos in self.calc_to_real(positions_dict).iteritems():
            real_axis = self._tagged[tag][0]
            move_dict[real_axis] = target_pos
        self._write_settings = True
        self._motion_control = True
        # force a global position update in case phys motors never move
        self._calc_from_real()
        self._reals_group.move(move_dict, wait=False)

    def calc_to_real(self, positions_dict):
        raise NotImplementedError

    def stop(self, axis):
        self._reals_group.stop()

    def read_position(self, axis):
        return axis.settings.get("dial_position")

    def state(self, axis, new_state=None):
        return self._reals_group.state()

    def set_position(self, axis, new_pos):
        if not axis in self.pseudos:
            raise RuntimeError("Cannot set dial position on motor '%s` from CalcController" % axis.name)

        positions = self._get_set_positions()
        positions[self._axis_tag(axis)] = new_pos
        real_positions = self.calc_to_real(positions)
        for real_axis_tag, user_pos in real_positions.iteritems():
            self._tagged[real_axis_tag][0].position(user_pos)

        self._calc_from_real()

        return axis.position()

