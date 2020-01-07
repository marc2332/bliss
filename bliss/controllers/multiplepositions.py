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
  target:
  - axis: $dummy1
    destination: 2.5
    tolerance: 0.01
- label: Cu2
  description: Copper 2 mm
  target:
  - axis: $dummy1
    destination: 2.0
    tolerance: 0.2
- label: Al4
  description: Aluminum 4 mm
  target:
  - axis: $dummy1
    destination: 3.5
    tolerance: 0.01

2. Beamstop with 3 predefined positions, moving 2 motors at the same time

class: MultiplePositions
name: beamstop
simultaneous_move: True
positions:
- label: IN
  description: Beamstop position IN the beam
  target:
  - axis: $dummy1
    destination: 2.5
    tolerance: 0.01
  - axis: $dummy2
    destination: 1.0
    tolerance: 0.2
- label: OUT
  description: Beamstop position OUT of the beam
  target:
  - axis: $dummy1
    destination: 3.5
    tolerance: 0.01
  - axis: $dummy2
    destination: 2.0
    tolerance: 0.2
- label: PARK
  description: Beamstop in safe position
  target:
  - axis: $dummy1
    destination: 1.5
    tolerance: 0.01
  - axis: $dummy2
    destination: 0.0
    tolerance: 0.2
"""
import functools

from tabulate import tabulate
from gevent import Timeout
from bliss.common.motor_group import Group
from bliss.common.axis import AxisState
from bliss.config.channels import Channel
from bliss.common import event
from bliss.common.logtools import log_warning, log_error
from bliss import global_map


class MultiplePositions:
    """ Handle multiple positions.
    """

    def __init__(self, name, config):
        self.simultaneous = True
        self.targets_dict = {}  # dict of all the targets (to be used by GUI)
        self.positions_list = []
        self._config = config
        self._group = None
        self.name = name
        self._last_label = None
        self._current_label = None
        self._position_channel = Channel(
            f"{name}:position",
            default_value="unknown",
            callback=self.__position_changed,
        )
        self._state_channel = Channel(
            f"{name}:state", default_value="READY", callback=self.__state_changed
        )
        self._read_config()

        # Add label-named method for all positions.
        for position in self.positions_list:
            self.add_label_move_method(position["label"])

        global_map.register(self, tag=name)

    def add_label_move_method(self, pos_label):
        """Add a method named after the position label to move to the
        corresponding position.
        """

        def label_move_func(mp_obj, pos):
            print(f"Moving '{mp_obj.name}' to position: {pos}")
            # display of motors values ?
            mp_obj.move(pos)

        # ACHTUNG: cannot start with a number...
        if pos_label.isidentifier():
            setattr(
                self,
                pos_label,
                functools.partial(label_move_func, mp_obj=self, pos=pos_label),
            )
        else:
            log_error(
                self, f"{self.name}: '{pos_label}' is not a valid python identifier."
            )

    def _read_config(self):
        """ Read the configuration.
        """
        self.targets_dict = {}
        self.positions_list = []
        try:
            for pos in self._config.get("positions"):
                self.positions_list.append(pos)
                self.targets_dict[pos.get("label")] = pos.get("target")
            self.simultaneous = self._config.get("move_simultaneous", True)
            _label = self.position
            if "unknown" not in self.position:
                self._current_label = _label
            if not (self._last_label and self._current_label):
                self._last_label = self.positions_list[0]["label"]
        except TypeError:
            print("No position configured")

    def __info__(self):
        """Standard method called by BLISS Shell info helper.
        Return the exhaustive status of the object.
        Returns:
            (str): tabulated string
        """
        # HEADER
        table = [("", "LABEL", "DESCRIPTION", "MOTOR POSITION(S)")]

        curr_pos = self._get_position()
        motpos_str = ""
        for pos in self.positions_list:
            descr = pos.get("description", "")
            if pos["label"] == curr_pos:
                mystr = "* "
            else:
                mystr = ""

            motstr = ""
            for mot in self.targets_dict[pos["label"]]:
                motstr += "%s: %3.3f  (± %2.3f)\n" % (
                    mot["axis"].name,
                    mot["destination"],
                    mot.get("tolerance", 0),
                )
                if mot["axis"].name not in motpos_str:
                    motpos_str += "%s = %3.4f\n" % (
                        mot["axis"].name,
                        mot["axis"].position,
                    )
            table.append((mystr, pos["label"], descr, motstr))
        # POSITIONS
        pos_str = tabulate(tuple(table), numalign="right", tablefmt="plain")

        return f"{pos_str}\n {motpos_str}"

    @property
    def position(self):
        """ Get the position of the object.
        Returns:
            (str): The position as defined in the label configuration parameter.
        """
        pos = self._get_position()
        if pos == self._current_label:
            self._last_label = pos
        return pos

    def __position_changed(self, pos):
        event.send(self, "position", pos)

    @property
    def state(self):
        """ Get the state of the object.
        Returns:
            (str): The state as a string.
        """
        return self._state_as_motor()._current_states[0]

    def __state_changed(self, sta):
        event.send(self, "state", sta)

    def _state_as_motor(self, label=None):
        """ The state as defined by the motor(s).
        Args:
            (str): The label. If not defined, the last known label will be used.
        Returns:
            (AxisState): The state as a motor state.
        """
        axis_list = []

        if self._group:
            return self._group.state
        if not label:
            label = self._current_label or self._last_label
            for axis in self.targets_dict[label]:
                axis_list.append(axis.get("axis"))
            grp = Group(*axis_list)
            return grp.state
        return AxisState("UNKNOWN")

    def __close__(self):
        for _, axes in self.targets_dict.items():
            for axis in axes:
                event.disconnect(axis["axis"], "move_done", self.__move_done)

    def move(self, label, wait=True):
        """ Move the motors to the destination, simultaneously or not,
            as defined in the config - move_simultaneously parameter
            (default value True).
            Wait the end of the move or not. Warning: only the simultaneosly
            moving motors can set wait=False. Otherwise the motors will move
            one after another in the order of the configuration file.
        Args:
            label (str): The label of the position to move to.
        Kwargs:
            wait (bool): Wait until the end of the movement of all the motors.
                         default value - True.
        Raises:
            RuntimeError: Wrong label
        """
        if label not in self.targets_dict:
            raise RuntimeError("%s is not a valid label" % label)
        self._current_label = label

        # create a group if motors move simultaneously
        if self.simultaneous:
            axis_list = []
            destination_list = []
            for axis in self.targets_dict[label]:
                axis_list.append(axis.get("axis"))
                destination_list.append(axis.get("destination"))

            self._group = Group(*axis_list)
            event.connect(self._group, "move_done", self.__move_done)
            try:
                self._group.move(dict(zip(axis_list, destination_list)), wait=wait)
            except Exception:
                event.disconnect(self._group, "move_done", self.__move_done)
                raise
        else:
            if not wait:
                log_warning(
                    self, "Motors will move one after another and not simultaneously."
                )
            for axis in self.targets_dict[label]:
                event.connect(axis.get("axis"), "move_done", self.__move_done)
                axis.get("axis").move(axis.get("destination"), wait=True)

    def __move_done(self, move_done):
        if move_done:
            event.disconnect(self._group, "move_done", self.__move_done)
            self._position_channel.value = self.position
            self._state_channel.value = "READY"
        else:
            self._position_channel.value = "unknown"
            self._state_channel.value = self.state

    def wait(self, timeout=None, label=None):
        """ Wait for the motors to finish their movement.
        Args:
            timeout(float): Timeout [s].
            label(str): Destination position label (only in case of
                                                    non silultaneous move).
        Raises:
            RuntimeError: Timeout while waiting for motors to move
        """
        if not label:
            label = self._current_label

        try:
            with Timeout(
                timeout, RuntimeError("Timeout while waiting for motors to move")
            ):
                if self._group:
                    self._group.wait_move()
                else:
                    for axis in self.targets_dict[label]:
                        axis.get("axis").wait_move()
        finally:
            if self._group:
                self._group.stop()
            else:
                for axis in self.targets_dict[label]:
                    axis.get("axis").stop()
            self.__state_changed(self.state)
            self.__position_changed(self.position)

    def stop(self):
        """ Stop all the moving motors.
        """
        if self._group:
            self._group.stop()
        else:
            for axis in self.targets_dict[self._current_label]:
                axis.get("axis").stop()
        self.__state_changed(self.state)
        self.__position_changed(self.position)

    def _in_position(self, motor_destination):
        """Check if the destination of a position is within the tolerance.
        Args:
            motor_destination(dict): The motor dictionary.
        Returns:
            (bool): True if on position.
        """

        tolerance = motor_destination.get("tolerance", 0)
        if (
            motor_destination.get("destination") - tolerance
            < motor_destination["axis"].position
            < motor_destination.get("destination") + tolerance
        ):
            return True
        return False

    @property
    def motors(self):
        """ Return dictionary {NAME: OBJECT} of all the axes.
        Returns:
            (dict): {string: Axis} dictionary.
        """
        _mot_dict = {}
        for motor in self.targets_dict.values():
            for idx, _ in enumerate(motor):
                if motor[idx]["axis"] not in _mot_dict:
                    _mot_dict.update({f'{motor[idx]["axis"].name}': motor[idx]["axis"]})
        return _mot_dict

    @property
    def motor_names(self):
        """Return list of NAMES of all the axes.
        Returns:
            (list): list of string(s).
        """
        return list(self.motors.keys())

    @property
    def motor_objs(self):
        """Return list of motors OBJECTS of all the axes.
        Returns:
            (list): Axis object(s) list.
        """
        return list(self.motors.values())

    def _get_position(self):
        """Read the postion.
        Returns:
            (str): The position label having all axes at destination.
                   Or 'unknown' if no valid position found.
        """
        # for all positions,
        for label, motor_destinations in self.targets_dict.items():
            in_position = []
            # check all destinations of this position.
            for motor_destination in motor_destinations:
                in_position.append(self._in_position(motor_destination))
            if all(in_position):
                self._last_label = label
                return label
        return "unknown"

    def update_position(self, label, motors_destinations_list=None, description=None):
        """ Update existing label to new motor position(s). If only the label
            specified, the current motor(s) position replaces the previous one.
        Args:
            label (str): The unique position label.
        Kwargs:
            motors_destinations_list (list): List of motor(s) or
                                          tuples (motor, position, tolerance).
                                          Important: motor is an Axis object.
                                          tolerance is optional
            description (str): The description of the position.
        Raises:
            TypeError: motors_destinations_list must be a list
            RuntimeError: Invalid label
        """
        if label not in self.targets_dict:
            raise RuntimeError("Invalid label")

        for elem in self._config["positions"]:
            if label == elem["label"]:
                idx = self._config["positions"].index(elem)
                break

        if description:
            self._config["positions"][idx]["description"] = description

        if motors_destinations_list:
            if not isinstance(motors_destinations_list, list):
                raise TypeError("motors_destinations_list must be a list")
            for element in motors_destinations_list:
                iii = motors_destinations_list.index(element)
                if isinstance(element, tuple):
                    if element[0] == self.targets_dict[label][iii]["axis"]:
                        self._config["positions"][idx]["target"][iii]["axis"] = element[
                            0
                        ]
                        self._config["positions"][idx]["target"][iii][
                            "destination"
                        ] = element[1]
                        try:
                            self._config["positions"][idx]["target"][iii][
                                "tolerance"
                            ] = element[2]
                        except IndexError:
                            pass
                else:
                    if element == self.targets_dict[label][iii]["axis"]:
                        self._config["positions"][idx]["target"][iii][
                            "destination"
                        ] = element.position
        else:
            for element in self.targets_dict[label]:
                iii = self.targets_dict[label].index(element)
                self._config["positions"][idx]["target"][iii]["axis"] = element["axis"]
                self._config["positions"][idx]["target"][iii]["destination"] = element[
                    "axis"
                ].position

        self._config.save()
        self._read_config()

    def create_position(self, label, motors_destinations_list, description=None):
        """ Create new position.
        Args:
            label (str): The unique position label.
            motors_destinations_list (list): List of motor(s) or
                                          tuples (motor, position, tolerance).
                                          Important: motor is an Axis object.
                                                     tolerance is optional.
            description (str): The description of the position.
        Raises:
            TypeError: motors_destinations_list must be a list
        """
        if label in self.targets_dict:
            raise RuntimeError("Label already exists. Please use update_position")
        target_list = []
        idx = len(self._config["positions"])
        self._config["positions"].append({"label": label})
        if description:
            self._config["positions"][idx].update({"description": description})

        if not isinstance(motors_destinations_list, list):
            raise TypeError("motors_destinations_list must be a list")

        for element in motors_destinations_list:
            if isinstance(element, tuple):
                try:
                    tolerance = element[2]
                except IndexError:
                    tolerance = 0
                target_list.append(
                    {
                        "axis": element[0],
                        "destination": element[1],
                        "tolerance": tolerance,
                    }
                )
            else:
                target_list.append(
                    {"axis": element, "destination": element.position, "tolerance": 0}
                )
            self._config["positions"][idx].update({"target": target_list})

        self._config.save()
        self._read_config()

    def remove_position(self, label):
        """ Remove position.
        Args:
            label (str): The unique position label.
        Raises:
            RuntimeError: Try to remove non existing position
        """
        if label not in self.targets_dict:
            raise RuntimeError("Try to remove non existing position")

        for elem in self._config["positions"]:
            if elem["label"] == label:
                self._config["positions"].remove(elem)
                break

        self._config.save()
        self._read_config()
