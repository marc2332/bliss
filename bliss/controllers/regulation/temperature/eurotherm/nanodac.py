# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
This class is the main controller of Eurotherm nanodac

yml configuration example:

- class: Nanodac
  plugin: regulation
  module: temperature.eurotherm.nanodac
  controller_ip: 160.103.30.184
  name: nanodac
  inputs:
    - name: nanodac_in1
      channel: 1
  outputs:
    - name: nanodac_out1
      channel: 1
  ctrl_loops:
    - name: nanodac_loop1
      channel: 1
      input: $nanodac_in1
      output: $nanodac_out1
"""

import weakref
import os
import time
import functools

import gevent

from bliss.controllers import regulator
from bliss.common import regulation
from bliss.common.counter import SamplingCounter

from bliss.comm import modbus
from .nanodac_mapping import name2address
from . import nanodac_mapping


def _nb_digit(raw_val, f_val):
    if int(raw_val) == int(f_val):
        return 0
    for i in range(1, 9):
        if abs(((raw_val / float(10 ** i)) - f_val)) < 1e-6:
            break
    return i


def _get_read_write(modbus, address_read_write):
    address, value_type = address_read_write
    if isinstance(address, tuple):
        address_read, value_type_read = address
        address_write, value_type_write, nb_digit = value_type

        def read(self):
            return modbus.read_holding_registers(address_read, value_type_read)

        def write(self, value, params={}):
            if value_type_write == "f":  # float write
                return modbus.write_float(address_write, value)
            else:
                digit = params.get("nb_digit", nb_digit)
                if not isinstance(digit, int):  # automatic digit case
                    raw_value = modbus.read_holding_registers(
                        address_write, value_type_write
                    )
                    float_value = modbus.read_holding_registers(
                        address_read, value_type_read
                    )
                    digit = _nb_digit(raw_value, float_value)
                    params["nb_digit"] = digit
                write_value = value * 10 ** digit
                return modbus.write_register(
                    address_write, value_type_write, write_value
                )

        return read, write
    else:
        if hasattr(nanodac_mapping, value_type):  # probably an enum
            enum_type = getattr(nanodac_mapping, value_type)

            def read(self):
                value = modbus.read_holding_registers(address, "b")
                return enum_type.get(value, "Unknown")

            def write(self, value):
                if isinstance(value, str):
                    for k, v in enum_type.items():
                        if v.lower() == value.lower():
                            value = k
                            break
                    else:
                        raise RuntimeError(
                            "Value %s is not in enum (%s)", value, enum_type.values()
                        )
                return modbus.write_register(address, "b", value)

        else:

            def read(self):
                return modbus.read_holding_registers(address, value_type)

            def write(self, value):
                return modbus.write_register(address, value_type, value)

        return read, write


def _create_attribute(filter_name, cls, instance, modbus):
    for name, address_read_write in name2address.items():
        if name.startswith(filter_name):
            subnames = name[len(filter_name) + 1 :].split(".")
            read, write = _get_read_write(modbus, address_read_write)
            if len(subnames) > 1:
                if subnames[0] == "main":
                    setattr(cls, subnames[1], property(read, write))
                elif getattr(instance, subnames[0], None) is None:
                    sub_cls = type(
                        ".".join([cls.__module__, cls.__name__, subnames[0]]), (), {}
                    )
                    child_instance = sub_cls()
                    _create_attribute(
                        filter_name + "." + subnames[0], sub_cls, instance, modbus
                    )
                    setattr(instance, subnames[0], child_instance)
            else:
                setattr(cls, subnames[0], property(read, write))


class nanodac(object):
    class SoftRamp(object):
        UP, DOWN = (1, -1)

        def __init__(self, nanodac, loop_number):
            self._loop = nanodac.get_loop(loop_number)
            self._slope = 1 / 60.  # default 1 deg / min
            self._targetsp = self._loop.targetsp
            self._ramp_task = None
            self._pipe = os.pipe()

        def __getattr__(self, name):
            return getattr(self._loop, name)

        @property
        def slope(self):
            return self._slope

        @slope.setter
        def slope(self, val):
            self._slope = val
            os.write(self._pipe[1], b"|")

        @property
        def workingsp(self):
            return self._loop.targetsp

        @property
        def targetsp(self):
            return self._targetsp

        @targetsp.setter
        def targetsp(self, val):
            self._started_targetsp = self._loop.pv
            self._targetsp = val
            self._direction = self.UP if val > self._started_targetsp else self.DOWN
            self._start_ramp = time.time()

            if self._ramp_task is None:
                self._ramp_task = gevent.spawn(self._run)
            else:
                os.write(self._pipe[1], b"|")

        @property
        def pv(self):
            return self._loop.pv

        @property
        def out(self):
            return self._loop.op.ch1out

        def stop(self):
            self._targetsp = self._loop.targetsp
            os.write(self._pipe[1], b"|")

        def _run(self):
            while abs(self._targetsp - self._loop.targetsp) > 0.1:
                wait_time = 0.1 / self._slope
                if wait_time < 0.:
                    wait_time = 0.
                fd, _, _ = gevent.select.select([self._pipe[0]], [], [], wait_time)
                if fd:
                    os.read(self._pipe[0], 1024)
                targetsp = (
                    self._slope * self._direction * (time.time() - self._start_ramp)
                    + self._started_targetsp
                )
                if (self._direction == self.UP and targetsp > self._targetsp) or (
                    self._direction == self.DOWN and targetsp < self._targetsp
                ):
                    targetsp = self._targetsp

                try:
                    self._loop.targetsp = round(targetsp, 1)
                except:
                    import traceback

                    traceback.print_exc()
                    break
            self._ramp_task = None

    def __init__(self, name, config_tree):
        self.name = name
        self._modbus = modbus.ModbusTcp(config_tree["controller_ip"])

    def _get_address(self, name):
        name_key = name.lower()
        try:
            address, value_type = name2address[name_key]
        except KeyError:
            raise RuntimeError("%s doesn't exist in address mapping" % name)
        else:
            return address, value_type

    def read(self, name):
        address, value_type = self._get_address(name)
        if isinstance(address, tuple):
            address, value_type = address
        return self._modbus.read_holding_registers(address, value_type)

    def write(self, name, value):
        address, value_type = self._get_address(name)
        if isinstance(address, tuple):
            address_read, value_read_type = address
            address, value_type, nb_digit = value_type
            if not isinstance(nb_digit, int):  # automatic nb_digit case
                raw_value = self._modbus.read_holding_registers(address, value_type)
                float_value = self._modbus.read_holding_registers(
                    address_read, value_read_type
                )
                nb_digit = _nb_digit(raw_value, float_value)
            value = value * 10 ** nb_digit
        self._modbus.write_register(address, value_type, value)

    def _get_handler(self, filter_name):
        cls = type(
            ".".join([self.__class__.__module__, self.__class__.__name__, filter_name]),
            (),
            {},
        )
        instance = cls()
        _create_attribute(filter_name, cls, instance, self._modbus)
        return instance

    def get_channel(self, channel_number):
        if 1 <= channel_number <= 4:
            return self._get_handler("channel.%d" % channel_number)
        else:
            raise RuntimeError("Nanodac doesn't have channel %d" % channel_number)

    def get_loop(self, loop_number):
        if 1 <= loop_number <= 2:
            return self._get_handler("loop.%d" % loop_number)
        else:
            raise RuntimeError("Nanodac doesn't have loop %d" % loop_number)

    def get_soft_ramp(self, loop_number):
        return self.SoftRamp(self, loop_number)


def _get_input_channel_from_config(func):
    @functools.wraps(func)
    def f(self, tinput):
        channel_nb = tinput.config.get("channel")
        if channel_nb is None:
            raise RuntimeError(
                f"Input {tinput.name} doesn't have **channel** set in config"
            )
        secondary = tinput.config.get("secondary", False)
        channel = self._controller.get_channel(channel_nb)
        return func(self, channel, secondary)

    return f


def _get_loop_from_config(func):
    @functools.wraps(func)
    def f(self, obj, *args):
        channel_nb = obj.config.get("channel")
        if channel_nb is None:
            raise RuntimeError(f"{obj.name} doesn't have **channel** set in config")
        loop = self._controller.get_loop(channel_nb)
        secondary = obj.config.get("secondary", False)
        return func(self, loop, secondary, *args)

    return f


class Nanodac(regulator.Controller):
    """
    Nanodac regulator controller.
    """

    def __init__(self, config):
        super().__init__(config)
        controller_ip = config.get("controller_ip")
        if controller_ip is None:
            raise RuntimeError("controller_ip musst be in configuration")
        self._controller = nanodac(config.get("name"), config)

    @_get_input_channel_from_config
    def read_input(self, channel, secondary):
        return channel.pv2 if secondary else channel.pv

    @_get_loop_from_config
    def read_output(self, loop, secondary):
        return loop.op.ch2out if secondary else loop.op.ch1out

    @_get_input_channel_from_config
    def state_input(self, channel, secondary):
        status_num = channel.status2 if secondary else channel.status
        STATUS_2_HUMAN = {
            0: "Ok",
            1: "Off",
            2: "Over range",
            3: "Under range",
            4: "Hardware error",
            5: "Ranging",
            6: "Overflow",
            7: "bad",
            8: "Hardware exceeded",
            9: "No data",
            12: "Comm channel error",
        }
        return STATUS_2_HUMAN.get(status_num, "Unknown")

    def state_output(self, toutput):
        return "Ok"

    def start_regulation(self, tloop):
        pass

    def stop_regulation(self, tloop):
        pass

    @_get_loop_from_config
    def get_setpoint(self, loop, secondary):
        return loop.targetsp

    @_get_loop_from_config
    def set_setpoint(self, loop, secondary, sp):
        loop.targetsp = sp

    @_get_loop_from_config
    def get_kp(self, loop, secondary):
        return loop.pid.proportionalband

    @_get_loop_from_config
    def get_ki(self, loop, secondary):
        return loop.pid.integraltime

    @_get_loop_from_config
    def get_kd(self, loop, secondary):
        return loop.pid.derivativetime

    @_get_loop_from_config
    def start_ramp(self, loop, secondary, sp, **kwargs):
        loop.automan = 0  # Activate the regulation 0=auto,1=manual
        loop.targetsp = sp

    @_get_loop_from_config
    def stop_ramp(self, loop, secondary):
        loop.targetsp = loop.pv

    @_get_loop_from_config
    def is_ramping(self, loop, secondary):
        return loop.targetsp != loop.workingsp

    @_get_loop_from_config
    def set_ramprate(self, loop, secondary, rate):
        loop.op.rate = rate

    @_get_loop_from_config
    def get_ramprate(self, loop, secondary):
        return loop.op.rate


class Loop(regulation.Loop):
    def __init__(self, controller, config):
        super().__init__(controller, config)
        channel_nb = config.get("channel")
        if channel_nb is None:
            raise RuntimeError(f"{self.name} doesn't have **channel** set in config")
        self.__loop = controller._controller.get_loop(channel_nb)
        self.create_counter(
            SamplingCounter,
            f"{self.name}_working_setpoint",
            unit=self.input.config.get("unit", "N/A"),
            mode="SINGLE",
        )

    def read_all(self, *counters):

        values = []
        for cnt in counters:
            if cnt.name.endswith("_working_setpoint"):
                values.append(self.__loop.workingsp)
            else:
                values.extend(super().read_all(cnt))
        return values
