# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.motor_config import MotorConfig
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import CalcCounterController
from bliss.comm.exceptions import CommunicationError

from functools import wraps
import weakref


def lazy_init(func):
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        if self.disabled:
            raise RuntimeError(f"Encoder {self.name} is disabled")
        try:
            self.controller._initialize_encoder(self)
        except Exception as e:
            if isinstance(e, CommunicationError):
                # also disable the controller
                self.controller._disabled = True
            self._disabled = True
            raise
        else:
            if not self.controller.encoder_initialized(self):
                # failed to initialize
                self._disabled = True
        return func(self, *args, **kwargs)

    return func_wrapper


class Encoder(SamplingCounter):
    def __init__(self, name, controller, motor_controller, config):
        super().__init__(name, controller, unit=config.get("unit"))
        self.__controller = motor_controller
        self.__config = MotorConfig(config)
        self.__axis_ref = None
        self._disabled = False

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
    def disabled(self):
        return self._disabled

    def enable(self):
        self._disabled = False
        self.raw_read

    @property
    @lazy_init
    def raw_read(self):
        return super().raw_read

    @property
    def counter(self):
        # TODO: deprecate this
        """Convenience access to the counter object

        Useful to set conversion function for example
        """
        return self  # backward compatibility

    @property
    def config(self):
        return self.__config

    @property
    @lazy_init
    def steps_per_unit(self):
        return self.config.get("steps_per_unit", float, 1)

    @property
    def tolerance(self):
        """
        Returns Encoder tolerance in user units.
        """
        return self.config.get("tolerance", float, 0)

    def read(self):
        """
        Returns encoder value *in user units*.
        """
        return self.raw_read  # backward compatibility

    @lazy_init
    def set(self, new_value):
        """
        <new_value> is in *user units*.
        """
        self.controller.set_encoder(self, new_value * self.steps_per_unit)
        return self.raw_read

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
        info_str += f"     dial_measured_position: {self.raw_read:10.5f}\n"
        return info_str


def encoder_noise_round(obs_value, expected_value, stepsize, noise):
    """
    Process the value to allow to use it as feedback:

    - removes digization
    - weights estimate if noise > 0

    Arguments:
        obs_value: the digital number coming from hardware
        expected_value: the value we expect to get based on setpoint
        stepsize: the digitization precision
        noise: typical read noise
    """
    diff = obs_value - expected_value
    diff_steps = diff / abs(stepsize)
    if abs(diff_steps) < 0.5:
        return expected_value
    if obs_value > expected_value:
        closest_allowed = obs_value - abs(stepsize) / 2.0
    else:
        closest_allowed = obs_value + abs(stepsize) / 2.0
    # weighting for obs vs calc. Quadratic weights.
    wt = noise * noise / (diff * diff + noise * noise)
    calc = (wt * expected_value) + (1 - wt) * closest_allowed
    # noise is high - take expected value
    # noise is low  - take observed value
    return calc


class EncoderFilter(CalcCounterController):
    """
    This calc controller creates 2 counters to return a filtered measured position
    from an encoder.
    
    Input counter:
       - encoder
    Output counters:
       - position:  *axis._set_position* if position is inside the **encoder_precision** or the encoder value.
       - position_error
    """

    def __init__(self, name, config):
        self._encoder = config["encoder"]
        assert isinstance(self._encoder, Encoder)

        config["inputs"] = [{"counter": self._encoder, "tags": "enc"}]
        config["outputs"] = [
            {"name": "position", "tags": "corrected_position"},
            {"name": "position_error", "tags": "error"},
        ]

        super().__init__(name, config)

    @property
    def encoder_precision(self):
        try:
            return float(self._config["encoder_precision"])
        except KeyError:
            return 0

    def calc_function(self, input_dict):
        encoder_value = corrected_value = input_dict["enc"]
        axis = self._encoder.axis
        if axis is not None:
            user_target_position = axis._set_position
            dial_target_position = axis.user2dial(user_target_position)
            encoder_stepsize = 1.0 / self._encoder.steps_per_unit
            encoder_precision = self.encoder_precision

            corrected_value = encoder_noise_round(
                encoder_value, dial_target_position, encoder_stepsize, encoder_precision
            )

        error = float("nan") if axis is None else dial_target_position - encoder_value

        return {"corrected_position": corrected_value, "error": error}
