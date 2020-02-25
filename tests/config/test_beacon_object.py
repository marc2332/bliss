# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import numpy
import pytest
import gevent
from bliss.config.beacon_object import BeaconObject
from bliss.common import event


class Ctrl(BeaconObject):
    def __init__(self, config):
        BeaconObject.__init__(self, config)
        self._speed, self._velocity = numpy.random.random(2)
        self._reading_speed = None
        self._mode = "blabla"

    @BeaconObject.property(must_be_in_config=True)
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        self._speed = value

    @BeaconObject.property
    def velocity(self):
        return self._velocity

    @velocity.setter
    def velocity(self, value):
        self._velocity = value

    @BeaconObject.property(default="quick")
    def reading_speed(self):
        return self._reading_speed

    @reading_speed.setter
    def reading_speed(self, value):
        self._reading_speed = value

    @BeaconObject.property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value

    @BeaconObject.lazy_init
    def check_lazy_init(self):
        return self._reading_speed is not None


@pytest.mark.parametrize(
    "ctrl_name", [("controller_setting1"), ("controller_setting2")]
)
def test_config_and_settings_basic_check(beacon, ctrl_name):
    cfg = beacon.get(ctrl_name)
    ctrl = Ctrl(cfg)
    settings_properties = ctrl._BeaconObject__settings_properties()
    link_cfg = {key: value for key, value in cfg.items() if key in settings_properties}
    assert link_cfg.items() <= dict(ctrl.settings).items()
    ctrl.speed = 42
    assert ctrl.settings["speed"] == 42
    assert ctrl.speed == 42
    ctrl._speed = 12
    assert ctrl.speed == 42
    ctrl.apply_config()
    assert ctrl.speed == cfg["speed"]
    cfg_speed = ctrl.speed
    ctrl.config["speed"] = 1234
    assert ctrl.speed == cfg_speed
    ctrl.apply_config()
    assert ctrl.speed == 1234
    ctrl.apply_config(reload=True)
    assert ctrl.speed == cfg_speed


def test_config_and_settings_check_missing_config(beacon):
    cfg = beacon.get("controller_setting1")
    cfg.pop("speed")
    ctrl = Ctrl(cfg)
    with pytest.raises(RuntimeError):
        ctrl.speed


@pytest.mark.parametrize(
    "ctrl_name", [("controller_setting1"), ("controller_setting2")]
)
def test_config_and_settings_check_default_and_taken_from_hardware(beacon, ctrl_name):
    cfg = beacon.get(ctrl_name)
    ctrl = Ctrl(cfg)
    assert ctrl.reading_speed != None
    assert ctrl.mode == ctrl._mode
    assert ctrl.settings["mode"] == ctrl._mode
    ctrl.mode = "truc"
    assert ctrl.mode == "truc"


def test_config_and_settings_lazy_init(beacon):
    cfg = beacon.get("controller_setting1")
    ctrl = Ctrl(cfg)
    assert ctrl.check_lazy_init()


class Ctrl2(BeaconObject):
    def __init__(self, config):
        BeaconObject.__init__(self, config)
        self._settling_time = None

    @BeaconObject.property(only_in_config=True)
    def settling_time(self):
        return self._settling_time

    @settling_time.setter
    def settling_time(self, value):
        self._settling_time = value


def test_config_and_settings_only_in_config(beacon):
    cfg = beacon.get("controller_setting1")
    ctrl = Ctrl2(cfg)
    with pytest.raises(RuntimeError):
        ctrl.settling_time
    cfg["settling_time"] = 100
    ctrl = Ctrl2(cfg)
    assert ctrl.settling_time == 100
    with pytest.raises(RuntimeError):
        ctrl.settling_time = 200
    assert ctrl.settling_time == 100


class Ctrl3(BeaconObject):
    _speed = BeaconObject.config_getter("speed")
    _velocity = BeaconObject.config_getter("velocity")


def test_config_and_settings_config_getter(beacon):
    cfg = beacon.get("controller_setting1")
    ctrl = Ctrl3(cfg)
    assert ctrl._speed == cfg.get("speed")
    assert ctrl._velocity == cfg.get("velocity")


class Ctrl4(BeaconObject):
    name = BeaconObject.config_getter("name")

    def __init__(self, config):
        BeaconObject.__init__(self, config)
        assert config.get("name") == self.name


def test_config_and_settings_config_getter_constructor(beacon):
    cfg = beacon.get("controller_setting1")
    ctrl = Ctrl4(cfg)
    assert ctrl.name


class Ctrl5(BeaconObject):
    name = BeaconObject.config_getter("name")

    @BeaconObject.property
    def velocity(self):
        return 20

    @velocity.setter
    def velocity(self, value):
        pass


class Ctrl6(Ctrl5):
    mode = BeaconObject.config_getter("mode")

    @BeaconObject.property
    def speed(self):
        return 10

    @speed.setter
    def speed(self, val):
        pass


def test_config_and_settings_inherited_class(beacon):
    cfg = beacon.get("controller_setting2")
    ctrl = Ctrl6(cfg)
    assert list(ctrl._BeaconObject__settings_properties().keys()) == [
        "velocity",
        "speed",
    ]
    assert list(ctrl._BeaconObject__config_getter().keys()) == ["name", "mode"]


class Ctrl7(BeaconObject):
    @BeaconObject.property(priority=2)
    def speed(self):
        return 10

    @speed.setter
    def speed(self, val):
        pass


class Ctrl8(Ctrl7):
    @BeaconObject.property
    def velocity(self):
        return 20

    @velocity.setter
    def velocity(self, val):
        pass

    @BeaconObject.property(priority=1)
    def mode(self):
        return "bla"

    @mode.setter
    def mode(self, value):
        pass


def test_config_and_settings_priority_test(beacon):
    cfg = beacon.get("controller_setting2")
    ctrl = Ctrl8(cfg)
    assert list(ctrl._BeaconObject__settings_properties().keys()) == [
        "velocity",
        "mode",
        "speed",
    ]


def test_event(beacon):
    cfg = beacon.get("controller_setting2")
    ctrl = Ctrl8(cfg)
    events_dict = {"nb": 0}
    current_values = dict()
    cbk_event = gevent.event.Event()

    def speed_cbk(value):
        current_values["speed"] = value
        cbk_event.set()
        events_dict["nb"] += 1

    def velocity_cbk(value):
        current_values["velocity"] = value
        cbk_event.set()
        events_dict["nb"] += 1

    def mode_cbk(value):
        current_values["mode"] = value
        cbk_event.set()
        events_dict["nb"] += 1

    def wait():
        with gevent.Timeout(1):
            while events_dict["nb"] < 3:
                cbk_event.wait()
                cbk_event.clear()
            events_dict["nb"] = 0

    event.connect(ctrl, "speed", speed_cbk)
    event.connect(ctrl, "velocity", velocity_cbk)
    event.connect(ctrl, "mode", mode_cbk)
    # Init
    ctrl.apply_config()
    wait()
    assert current_values == {"speed": 20, "velocity": 1.9, "mode": "fixed"}

    ctrl.speed = 100
    ctrl.velocity = 0.3
    ctrl.mode = "Hello"
    wait()
    assert current_values == {"speed": 100, "velocity": .3, "mode": "Hello"}


class Ctrl10(BeaconObject):
    waittime = BeaconObject.property_setting("waittime", default=0.)
    none_init = BeaconObject.property_setting("none_init")


def test_property_settings(beacon):
    cfg = beacon.get("controller_setting2")
    ctrl = Ctrl10(cfg)
    assert ctrl.waittime == 0.
    ctrl.waittime = 12.2
    assert ctrl.waittime == 12.2

    assert ctrl.none_init is None


class Ctrl11(BeaconObject):
    position = BeaconObject.property_setting("position", default=0.)
    speed = BeaconObject.property_setting("speed", default=0)
    velocity = BeaconObject.property_setting("velocity")


def test_BeaconObject_path(beacon):
    cfg = beacon.get("hello_ctrl")
    ctrl = Ctrl11(cfg, path=["something", "something_else"], share_hardware=False)
    assert ctrl.speed == 10
    assert ctrl.velocity == 1.2

    ctrl.speed = 13
    assert ctrl.speed == 13

    ctrl.apply_config()
    assert ctrl.speed == 10

    ctrl.speed = 14
    assert ctrl.speed == 14

    ctrl.apply_config(reload=True)
    assert ctrl.speed == 10

    ctrl = Ctrl11(cfg, path=["something", "does_not_exist"], share_hardware=False)
    assert ctrl.speed == 0


def test_BeaconObject_name(beacon):
    cfg = beacon.get("controller_setting1")
    ctrl = Ctrl3(cfg)
    assert ctrl.name == "controller_setting1"

    cfg = beacon.get("hello_ctrl")
    ctrl = Ctrl11(cfg, path=["something", "something_else"], share_hardware=False)
    assert ctrl.name == "hello_ctrl_something_something_else"

    ctrl = Ctrl11(
        cfg,
        name="my_custom_name",
        path=["something", "something_else"],
        share_hardware=False,
    )
    assert ctrl.name == "my_custom_name"

    class MyCtrl(Ctrl11):
        def __init__(self, config, path=None):
            self.name = "my_custom_ctrl_name"
            Ctrl11.__init__(self, config, path, share_hardware=False)

    ctrl = MyCtrl(cfg, path=["something", "something_else"])
    assert ctrl.name == "my_custom_ctrl_name"


def test_beacon_object_2_processes(beacon):
    cfg = beacon.get("controller_setting2")
    ctrl = Ctrl8(cfg)

    assert ctrl.mode

    # simulate a second process
    ctrl_from_another_process = Ctrl8(cfg)

    assert ctrl_from_another_process.mode


def test_beacon_object_within_lima(default_session, lima_simulator):
    # test for issue 1383
    lima_simulator = default_session.config.get("lima_simulator")

    lima_simulator._image_params.flip = [True, True]

    assert lima_simulator._image_params.flip == [True, True]

    lima_simulator._image_params.flip = [False, False]
