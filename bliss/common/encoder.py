# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.motor_config import StaticConfig
from bliss.common.counter import SamplingCounter
from bliss.controllers import counter
from bliss.common import event
from functools import wraps
import time
import gevent
import re
import types
import weakref


class Encoder:
    def lazy_init(func):
        @wraps(func)
        def func_wrapper(self, *args, **kwargs):
            self.controller._initialize_encoder(self)
            return func(self, *args, **kwargs)

        return func_wrapper

    def __init__(self, name, controller, config):
        self.__name = name
        self.__controller = controller
        self._counter_controller = counter.SamplingCounterController(name)
        # note: read_all is not implemented, multiple encoders from the same controller will not be read in one go
        self._counter_controller.read_all = types.MethodType(
            self._read_all_counters, self._counter_controller
        )
        self._counter_controller.create_counter(
            SamplingCounter, "position", unit=config.get("unit")
        )
        self.__config = StaticConfig(config)
        self.__axis_ref = None

    @property
    def name(self):
        return self.__name

    @property
    def controller(self):
        return self.__controller

    @property
    def axis(self):
        if self.__axis_ref is not None:
            return self.__axis_ref()

    @axis.setter
    def axis(self, axis):
        if axis is not None:
            self.__axis_ref = weakref.ref(axis)

    @property
    def counters(self):
        """CounterContainer protocol"""
        return self._counter_controller.counters

    @property
    def counter(self):
        """Convenience access to the counter object

        Useful to set conversion function for example
        """
        return self._counter_controller.counters[0]

    @property
    def config(self):
        return self.__config

    @property
    def steps_per_unit(self):
        return self.config.get("steps_per_unit", float, 1)

    @property
    def tolerance(self):
        """
        Returns Encoder tolerance in user units.
        """
        return self.config.get("tolerance", float, 0)

    @lazy_init
    def read(self):
        """
        Returns encoder value *in user units*.
        """
        return self.controller.read_encoder(self) / float(self.steps_per_unit)

    @lazy_init
    def _read_all_counters(self, counter_controller, *counters):
        """
        This method can be inherited to read other counters
        from Encoder
        """
        return [self.read()]

    @lazy_init
    def set(self, new_value):
        """
        <new_value> is in *user units*.
        """
        self.controller.set_encoder(self, new_value * self.steps_per_unit)
        return self.read()

    @lazy_init
    def set_event_positions(self, positions):
        return self.__controller.set_event_positions(self, positions)

    @lazy_init
    def get_event_positions(self, positions):
        return self.__controller.get_event_positions(self)

    @lazy_init
    def __info__(self):
        info_str = "ENCODER:\n"
        info_str += f"     tolerance (to check pos at end of move): {self.tolerance}\n"
        info_str += f"     dial_measured_position: {self.read():10.5f}\n"
        return info_str


class EncoderFilter(Encoder):
    """
    This encoder return a measure position which is filtered.
    return the *axis._set_position* if position is inside the **encoder_precision**
    or the encoder value.
    """

    POSSIBLE_COUNTERS = ["position_raw", "position_error"]

    def __init__(self, name, controller, config):
        super().__init__(name, controller, config)
        enable_counters = config.get("enable_counters", [])
        for cnt_name in enable_counters:
            if cnt_name not in EncoderFilter.POSSIBLE_COUNTERS:
                raise ValueError(
                    f"Counter can't be {cnt_name} only "
                    f"be in {EncoderFilter.POSSIBLE_COUNTERS}"
                )
            self._counter_controller.create_counter(
                SamplingCounter, cnt_name, unit=config.get("unit")
            )

    def read(self):
        return self._read_all_counters(self._counter_controller, self.counter)[0]

    @Encoder.lazy_init
    def _read_all_counters(self, counter_controller, *counters):
        """
        This method can be inherited to read other counters
        from Encoder
        """
        encoder_value = super().read()
        corrected_value = encoder_value
        axis = self.axis
        if axis is not None:
            user_target_position = axis._set_position
            dial_target_position = axis.user2dial(user_target_position)
            encoder_precision = self.config.get("encoder_precision", float, 0.5)
            min_range = encoder_value - encoder_precision
            max_range = encoder_value + encoder_precision
            if min_range <= dial_target_position <= max_range:
                corrected_value = dial_target_position

        values = list()
        for cnt in counters:
            if cnt.name == "position":
                values.append(corrected_value)
            elif cnt.name == "position_raw":
                values.append(encoder_value)
            elif cnt.name == "position_error":
                if axis is None:
                    values.append(float("nan"))
                else:
                    values.append(dial_target_position - encoder_value)
        return values
