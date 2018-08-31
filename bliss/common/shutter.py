# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools

from gevent import lock

from bliss.config.conductor.client import Lock
from bliss.config.channels import Cache, Channel
from bliss.config.settings import HashObjSetting
from bliss.common.switch import Switch as BaseSwitch


class ShutterSwitch(BaseSwitch):
    def __init__(self, set_open, set_closed, is_opened):
        BaseSwitch.__init__(self, "ShutterSwitch" + str(id(self)), {})

        self._set_open = set_open
        self._set_closed = set_closed
        self._is_opened = is_opened

    def _states_list(self):
        return ["OPEN", "CLOSED"]

    def _set(self, state):
        if state == "OPEN":
            return self._set_open()
        else:
            return self._set_closed()

    def _get(self):
        if self._is_opened():
            return "OPEN"
        else:
            return "CLOSED"


class Shutter(object):
    MANUAL, EXTERNAL, CONFIGURATION = range(3)  # modes
    MODE2STR = {
        MANUAL: ("MANUAL", "Manual mode"),
        EXTERNAL: ("EXTERNAL", "External trigger mode"),
        CONFIGURATION: ("CONFIGURATION", "Configuration mode"),
    }
    OPEN, CLOSED, UNKNOWN = range(3)  # state
    STATE2STR = {
        OPEN: ("OPEN", "Shutter is open"),
        CLOSED: ("CLOSED", "Shutter is closed"),
        UNKNOWN: ("UNKNOWN", "Unknown shutter state"),
    }

    """
    Generic shutter object

    This interface should be used for all type of shutter (motor,fast...)

    You may want to link this shutter with an external
    control i.e: wago,musst.... in that case you have to put
    in configuration **external-control** with the object reference.
    This external control should be compatible with the Switch object
    and have an OPEN/CLOSED states.
    """

    def lazy_init(func):
        @functools.wraps(func)
        def func_wrapper(self, *args, **kwargs):
            self.init()
            with Lock(self):
                return func(self, *args, **kwargs)

        return func_wrapper

    def __init__(self, name, config):
        self.__name = name
        self.__config = config
        self._external_ctrl = config.get("external-control")
        self.__settings = HashObjSetting("shutter:%s" % name)
        self.__initialized_hw = Cache(self, "initialized", default_value=False)
        self.__state = Cache(self, "state", default_value=Shutter.UNKNOWN)
        self.__shutter_state = Channel(
            name + ":shutter_state", default_value=Shutter.UNKNOWN
        )
        self._init_flag = False
        self.__lock = lock.Semaphore()

    def init(self):
        """
        initialize the shutter in the current mode.
        this is method is called by lazy_init
        """
        if self._external_ctrl is not None:
            # Check if the external control is compatible
            # with a switch object and if it has open/close state
            ext_ctrl = self._external_ctrl
            name = ext_ctrl.name if hasattr(ext_ctrl, "name") else "unknown"
            try:
                states = ext_ctrl.states_list()
                ext_ctrl.set
                ext_ctrl.get
            except AttributeError:
                raise ValueError(
                    "external-ctrl : {0} is not compatible "
                    "with a switch object".format(name)
                )
            else:
                if not "OPEN" in states or not "CLOSED" in states:
                    raise ValueError(
                        "external-ctrl : {0} doesn't"
                        " have 'OPEN' and 'CLOSED' states".format(name)
                    )

        if not self._init_flag:
            self._init_flag = True
            try:
                self._init()
                with Lock(self):
                    with self.__lock:
                        if not self.__initialized_hw.value:
                            self._initialize_hardware()
                            self.__initialized_hw.value = True
            except:
                self._init_flag = False
                raise

    def _init(self):
        """
        This method should contains all software initialization
        like communication, internal state...
        """
        raise NotImplementedError

    def _initialize_hardware(self):
        """
        This method should contains all commands needed to
        initialize the hardware.
        It's will be call only once (by the first client).
        """
        pass

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def settings(self):
        return self.__settings

    @property
    def mode(self):
        """
        shutter mode can be MANUAL,EXTERNAL,CONFIGURATION
        
        In CONFIGURATION mode, shutter can't be opened/closed.
        **CONFIGURATION** could mean that the shutter is in tuning mode
        i.e: changing open/close position in case of a motor.

        In EXTERNAL mode, the shutter will be controlled
        through the external-control handler.
        If no external control is configured open/close
        won't be authorized.
        """
        return self.__settings.get("mode", Shutter.MANUAL)

    @mode.setter
    def mode(self, value):
        if value not in self.MODE2STR:
            raise ValueError(
                "Mode can only be: %s"
                % ",".join((x[0] for x in self.MODE2STR.values()))
            )
        self.init()
        self._set_mode(value)
        if value in (self.CONFIGURATION, self.EXTERNAL):
            # Can't cache the state if external or configuration
            self.__state.value = self.UNKNOWN
        self.__settings["mode"] = value

    def _set_mode(self, value):
        raise NotImplementedError

    @property
    def state(self):
        self.init()
        mode = self.mode
        if mode == self.MANUAL and self.__state.value == self.UNKNOWN:
            return_state = self._state()
            self.__state.value = return_state
            return return_state
        else:
            if mode == self.EXTERNAL:
                if self.external_control is not None:
                    switch_state = self.external_control.get()
                    return self.OPEN if switch_state == "OPEN" else self.CLOSED
                else:
                    return self.UNKNOWN
            elif mode == self.CONFIGURATION:
                return self.UNKNOWN
            return self.__state.value

    def _state(self):
        raise NotImplementedError

    @property
    def state_string(self):
        return self.STATE2STR.get(self.state, self.STATE2STR[self.UNKNOWN])

    @property
    def is_open(self):
        return self.state == self.OPEN

    @property
    def is_closed(self):
        return self.state == self.CLOSED

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def external_control(self):
        return self._external_ctrl

    @lazy_init
    def opening_time(self):
        """
        Return the opening time if available or None
        """
        return self._opening_time()

    def _opening_time(self):
        return self.__settings.get("opening_time")

    @lazy_init
    def closing_time(self):
        """
        Return the closing time if available or None
        """
        return self._closing_time()

    def _closing_time(self):
        return self.__settings.get("closing_time")

    def measure_open_close_time(self):
        """
        This small procedure will in basic usage do an open and close
        of the shutter to measure the opening and closing time.
        Those timing will be register into the settings.
        returns (opening,closing) time
        """
        previous_mode = self.mode()
        try:
            if previous_mode != self.MANUAL:
                self.mode(self.MANUAL)
            opening_time, closing_time = self._measure_open_close_time()
            self.__settings["opening_time"] = opening_time
            self.__settings["closing_time"] = closing_time
            return open_time, close_time
        finally:
            if previous_mode != self.MANUAL:
                self.mode(previous_mode)

    def _measure_open_close_time(self):
        """
        This method can be overloaded if needed.
        Basic timing on 
        """
        self.close()  # ensure it's closed
        start_time = time.time()
        self.open()
        opening_time = time.time() - start_time

        start_time = time.time()
        self.close()
        closing_time = time.time() - start_time
        return opening_time, closing_time

    @lazy_init
    def open(self):
        mode = self.mode
        if mode == self.EXTERNAL:
            if self._external_ctrl is None:
                raise RuntimeError(
                    "Can't open the shutter because no "
                    "external-control is configured"
                )
            else:
                ret = self._external_ctrl.set("OPEN")
        elif mode != self.MANUAL:
            raise RuntimeError(
                "Can't open the shutter, in %s" % self.MODE2STR.get(mode, "Unknown")
            )
        else:
            ret = self._open()
        self.__shutter_state.value = self.state
        return ret

    def _open(self):
        raise NotImplementedError

    @lazy_init
    def close(self):
        mode = self.mode
        if mode == self.EXTERNAL:
            if self._external_ctrl is None:
                raise RuntimeError(
                    "Can't close the shutter because no "
                    "external-control is configured"
                )
            else:
                ret = self._external_ctrl.set("CLOSED")
        elif mode != self.MANUAL:
            raise RuntimeError(
                "Can't close the shutter, in %s" % self.MODE2STR.get(mode, "Unknown")
            )
        else:
            ret = self._close()
        self.__shutter_state.value = self.state
        return ret

    def _close(self):
        raise NotImplementedError

    def set_external_control(self, set_open, set_closed, is_opened):
        """
        Programmatically set shutter in external control mode,
        and create _external_ctrl switch using callback functions
        """
        if not all(map(callable, (set_open, set_closed, is_opened))):
            raise TypeError(
                "%s.set_external_control: set_open, set_closed, is_opened functions must be callable"
                % self.name
            )
        switch = ShutterSwitch(set_open, set_closed, is_opened)
        self._external_ctrl = switch
        self.init()
