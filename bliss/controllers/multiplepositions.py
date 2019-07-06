# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Handle multiple, predefined motor positions equpment.

Example YAML_ configuration:

1. Attenuator with 3 predefined positions, moving 1 motor (dummy1)

class: MultiplePositions
name: att1
positions:
- label: Al3
  description: Aluminum 3 mm
  axes:
  - axis: $dummy1
    target: 2.5
    delta: 0.01
- label: Cu2
  description: Copper 2 mm
  axes:
  - axis: $dummy1
    target: 2.0
    delta: 0.2
- label: Al4
  description: Aluminum 4 mm
  axes:
  - axis: $dummy1
    target: 3.5
    delta: 0.01

2. Beamstop with 3 predefined positions, moving 2 motors at the same time

class: MultiplePositions
name: beamstop
simultaneous_move: True
positions:
- label: IN
  description: Beamstop position IN the beam
  axes:
  - axis: $dummy1
    target: 2.5
    delta: 0.01
  - axis: $dummy2
    target: 1.0
    delta: 0.2
- label: OUT
  description: Beamstop position OUT of the beam
  axes:
  - axis: $dummy1
    target: 3.5
    delta: 0.01
  - axis: $dummy2
    target: 2.0
    delta: 0.2
- label: PARK
  description: Beamstop in safe position
  axes:
  - axis: $dummy1
    target: 1.5
    delta: 0.01
  - axis: $dummy2
    target: 0.0
    delta: 0.2
"""
from gevent import Timeout
from bliss.common.motor_group import Group
from bliss.common import session
from bliss.common.logtools import *


class MultiplePositions:
    """ Handle multiple positions
    """

    def __init__(self, name, config):
        self.motors = {}
        self.labels_list = []
        self._config = config
        self.__lbl_max = 0
        self.__desc_max = 0
        self.simultaneous = True
        self.group = None
        session.get_current().map.register(self, tag=name)
        self._create_config()

    def _create_config(self):
        """ Read the configuration. Create nesessary variables
        """
        self.motors = {}
        self.labels_list = []
        try:
            for pos in self._config.get("positions"):
                pos = pos.to_dict()
                if len(pos.get("label")) > self.__lbl_max:
                    self.__lbl_max = len(pos.get("label"))
                if len(pos.get("description")) > self.__desc_max:
                    self.__desc_max = len(pos.get("description"))
                self.labels_list.append(pos)
                self.motors[pos.get("label")] = pos.get("axes")
        except TypeError:
            print("No position configured")
        self.simultaneous = self._config.get("move_simultaneous", True)

    def status(self):
        """ Print the exhaustive status of the object
        """
        print(
            "  LABEL%sDESCRIPTION%sMOTOR POSITION(S)"
            % (" " * max(self.__lbl_max - 1, 4), " " * max(self.__desc_max - 7, 4))
        )
        curr_pos = self._get_position()
        for pos in self.labels_list:
            mystr = "  "
            if pos["label"] in curr_pos:
                mystr = "* "
            mystr += (
                pos["label"]
                + " " * (max(self.__lbl_max, 5) - len(pos["label"]) + 4)
                + pos["description"]
                + " " * (max(self.__desc_max, 11) - len(pos["description"]) + 3)
            )
            mstr = ""
            motstr = ""
            n = 0
            for mot in self.motors[pos["label"]]:
                if n:
                    mstr += " " * (len(mystr) + 1)
                mstr += "%s: %3.3f  (± %2.3f)\n" % (
                    mot["axis"].name,
                    mot["target"],
                    mot.get("delta", 0),
                )
                motstr += "%s = %3.4f\n" % (mot["axis"].name, mot["axis"].position)
                n += 1
            print(mystr, mstr)
        print(motstr)

    @property
    def position(self):
        """ Get the position of the object
        Returns:
            (str): The position as defined in the label configuration parameter
        """
        return self._get_position()

    def move(self, label, wait=True):
        """ Move the motors to the target, simultaneously or not, as defined in
            the config - move_siimultaneously parameter (default value True).
            Wait the end of the move or not. Warning: only the simultaneosly
            moving motors can set wait to False. Otherwise the motors will be
            moved one after another in the order of the configuration file.
        Args:
            label (str): The label of the position to move to
        Kwargs:
            wait (bool): Wait until the end of the movement of all the motors.
                         default value - True.
        Raises:
            RuntimeError: Wrong label
        """
        if label not in self.motors:
            raise RuntimeError("%s is not a valid label" % label)

        # create a group if motors move simultaneously
        if self.simultaneous:
            axis_list = []
            target_list = []
            for axis in self.motors[label]:
                axis_list.append(axis.get("axis"))
                target_list.append(axis.get("target"))

            self.group = Group(*axis_list)
            self.group.move(dict(zip(axis_list, target_list)), wait=wait)
        else:
            if not wait:
                log_warning(
                    self, "Motors will move one after another and not simultaneously."
                )
            for axis in self.motors[label]:
                axis.get("axis").move(axis.get("target"), wait=True)

    def wait(self, label=None, timeout=None):
        """ Wait for the motors to finish their movement.
        Args:
            label(str): Destination position label (only in case of
                                                    non silultaneous move)
            timeout(float): Timeout [s]
        Raises:
            RuntimeError: Timeout while waiting for motors to move.
                          No label (if appropriate)
        """
        try:
            with Timeout(
                timeout, RuntimeError("Timeout while waiting for motors to move")
            ):
                if self.group:
                    self.group.wait_move()
                else:
                    for axis in self.motors[label]:
                        axis.get("axis").wait_move()
        except KeyError:
            raise RuntimeError("No label")
        finally:
            if self.group:
                self.group.stop()
            else:
                try:
                    for axis in self.motors[label]:
                        axis.get("axis").stop()
                except KeyError:
                    raise RuntimeError("No label")

    def _in_position(self, motor):
        """Check if the positions of a motor is within the tolerance
        Args:
            motor(dict): The motor dictionary
        Returns:
            (bool): True if on position
        """

        delta = motor.get("delta", 0)
        if (
            motor.get("target") - delta
            < motor["axis"].position
            < motor.get("target") + delta
        ):
            return True
        return False

    def _get_position(self):
        """Read the postion
        Returns:
            (str): The position label or "unknown"
        """
        for lbl, value in self.motors.items():
            in_position = []
            for mot in value:
                in_position.append(self._in_position(mot))
            if all(in_position):
                return lbl
        return "unknown"

    def update_position(self, label, motors_positions_list=None):
        """ Update existing label to new motor position(s). If only the label
            specified, the current motor(s) position replaces the previos one.
        Args:
            label (str): The unique position label
        Kwargs:
            motors_positions_list (list): List of motor(s) or
                                          tuples (motor, position).
                Motors are Axis objects.
        Raises:
            TypeError: motors_positions_list must be a list
            RuntimeError: Invalid label
        """
        if label not in self.motors.keys():
            raise RuntimeError("Invalid label")

        for elem in self._config["positions"]:
            if label == elem["label"]:
                idx = self._config["positions"].index(elem)
                break

        if motors_positions_list:
            if not isinstance(motors_positions_list, list):
                raise TypeError("motors_positions_list must be a list")
            for element in motors_positions_list:
                if isinstance(element, tuple):
                    for ii in range(len(self.motors[label])):
                        if element[0] == self.motors[label][ii]["axis"]:
                            self._config["positions"][idx]["axes"][ii][
                                "axis"
                            ] = element[0]
                            self._config["positions"][idx]["axes"][ii][
                                "target"
                            ] = element[1]
                else:
                    for ii in range(len(self.motors[label])):
                        if element == self.motors[label][ii]["axis"]:
                            self._config["positions"][idx]["axes"][ii][
                                "target"
                            ] = element.position
        else:
            for ii in range(len(self.motors[label])):
                self._config["positions"][idx]["axes"][ii]["axis"] = self.motors[label][
                    ii
                ]["axis"]
                self._config["positions"][idx]["axes"][ii]["target"] = self.motors[
                    label
                ][ii]["axis"].position

        self._config.save()
        self._create_config()
