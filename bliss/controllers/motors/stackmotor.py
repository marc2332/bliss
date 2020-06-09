# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import ast

from bliss import global_map
from bliss.common.logtools import log_debug
from bliss.common.utils import object_method
from bliss.controllers.motor import CalcController


"""
controller:
  - module: stackmotor
    class: StackMotor
    axes:
      # large stroke motor
      - name: $m1
        tags: real mls
  
      # small stroke motor
      - name: $m2
        tags: real mss
        # low and high limits
        low_limit: -1
        high_limit: 1
        # absolute limits:
        #   if False, limits are calculated from the current position when stack is enabled
        #   at startup stack is enabled
        absolute_limits: False
  
      - name: mstack
        tags: stack
        unit: mrad
"""


class StackMotor(CalcController):
    """
    A Stackmotor consists in a pair of motors mounted on top of each other,
    - one motor with a large stroke (fast but not very precise)
    - and one with a short stroke (slow but very precise).
    
    A StackMotor can be (de)activated with `stack_on` & `stack_off`.
    - when inactive only the large motor will move when moving the stack
    - when active, the small motor will make the move if it stays within its limits,
      otherwise small motor is moved to its middle position and the large motor makes the move.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in ast.literal_eval(self.config.get("axes")):
            if "real mls" in i.values():
                self.mls = i["name"][1:]
            if "real mss" in i.values():
                self.mss = i["name"][1:]
                self.mss_low_limit = float(i["low_limit"])
                self.mss_high_limit = float(i["high_limit"])
                self.absolute_limits = bool(i["absolute_limits"])
            if "stack" in i.values():
                self.stackmotor = i["name"]
        self.stack_active = True

    @object_method()
    def stack_on(self, _):
        """
        Activate the stack:
        When active and moving the stack, the short motor alone will be moved if it remains within its limits,
        when moving outside its limits, it will be moved into its middle position and the move will be made with the large motor.
        """
        self.stack_active = True
        if not self.absolute_limits:
            p = [
                i[1] for i in global_map.get_axes_positions_iter() if i[0] == self.mss
            ][0]
            self.mss_low_limit += p
            self.mss_high_limit += p

    @object_method()
    def stack_off(self, _):
        """
        Dectivate the stack:
        when inactive, only the large motor will move when moving the stack, the small motor will not move.
        """
        self.stack_active = False

    def __info__(self):
        s = (
            "STACK MOTOR:\n"
            + f"     large stroke motor: {self.mls}\n"
            + f"     small stroke motor: {self.mss} in [{self.mss_low_limit},{self.mss_high_limit}]\n"
            + f'     stack is {["OFF","ON"][self.stack_active]}\n'
            + f"     {self.stackmotor} = {self.mls} + {self.mss}\n"
        )
        return s

    def calc_from_real(self, positions_dict):
        log_debug(self, "calc_from_real: received positions:\n", positions_dict)

        calc_dict = dict()
        calc_dict.update({"stack": positions_dict["mls"] + positions_dict["mss"]})
        return calc_dict

    def calc_to_real(self, positions_dict):
        ### TODO handle numpy arrays (#1622)

        log_debug(self, "calc_to_real: received positions:\n", positions_dict)

        real_dict = dict()

        # build dict of current positions
        pos = {
            motor: position
            for motor, position in zip(
                [i.name for i in self.reals], [i.position for i in self.reals]
            )
        }
        # calculate position of small and large stroke motors
        if self.stack_active:
            delta = positions_dict["stack"] - pos[self.mls] - pos[self.mss]
            if (
                pos[self.mss] + delta > self.mss_low_limit
                and pos[self.mss] + delta < self.mss_high_limit
            ):
                # move is made with small stroke motor
                mss_target = pos[self.mss] + delta
                mls_target = pos[self.mls]
            else:
                # small stroke motor is brought back to middle position
                mss_target = (self.mss_low_limit + self.mss_high_limit) / 2
                mls_target = positions_dict["stack"] - mss_target
        else:
            mss_target = pos[self.mss]
            mls_target = positions_dict["stack"] - mss_target

        real_dict.update({"mls": mls_target, "mss": mss_target})

        return real_dict
