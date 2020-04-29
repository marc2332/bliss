# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
The ESRF white beam attenuators are motor driven coper poles with sevaral
holes/filters.
Each attenuator pole has positive/negative limit switch and a home switch
active for each filter. The configuration procedure tries to find
the home switchwes and set the position of each filetr at the middle of the
home switch position.

Example YAML_ configuration:

  name: wba
  plugin: bliss
  class: WhiteBeamAttenuator
  attenuators:
    - attenuator: $wba_Al
    - attenuator: $wba_Mo
    - attenuator: $wba_Cu

Each attenuator pole has to be configured as bliss MultiplePosition onject.
"""
from bliss import global_map
from bliss.common import event
from bliss.common.utils import grouped
from bliss.common.logtools import log_info, log_error
from bliss.controllers.tango_shutter import TangoShutterState
from bliss.common.hook import MotionHook


class FeMotionHook(MotionHook):
    def __init__(self, frontend):
        self.frontend = frontend

    def pre_move(self, motion_list):
        if self.frontend.state not in (
            TangoShutterState.CLOSED,
            TangoShutterState.FAULT,
            TangoShutterState.DISABLE,
        ):
            raise RuntimeError("Cannot move motor when frontend is not on a safe state")


class CheckHook(MotionHook):
    def __init__(self, axis):
        self.axis = axis  # consider weakref
        self.state_changes = []
        # connect event self.__call__ to motor state
        event.connect(self.axis, "state", self)

    def pre_move(self, motion_list):
        if "HOME" not in self.axis.state:
            log_error(self, "Axis %s did not start from HOME position", self.axis.name)

    def post_move(self, motion_list):
        # cleaning event
        event.disconnect(self.axis, "state", self)
        # remove the hook itself
        self.axis.motion_hooks.remove(self)

        # reporting errors
        if "HOME" not in self.axis.state:
            log_error(self, "Axis %s did not stop on HOME position", self.axis.name)
        if not any(
            "MOVING" in state and "HOME" not in state
            for state in self.state_changes[1:]
        ):
            # check if the motor is really going out of home
            log_error(self, "Axis %s did not leave HOME switch", self.axis.name)

    def __call__(self, state):
        log_info(self, "Changing axis state to %s", state)
        self.state_changes.append(state)


class WhiteBeamAttenuator:
    """Methods to control White Beam Attenuator."""

    def __init__(self, name, config):
        self.attenuators = config.get("attenuators")
        self.__name = name
        global_map.register(self, tag=name)

        self._add_frontend_hooks(config.get("frontend"))

    def _add_frontend_hooks(self, frontend):
        if not frontend:
            return
        if not hasattr(frontend, "state") or frontend.state not in TangoShutterState:
            raise RuntimeError("Could not create Frontend hook")

        for att in self.attenuators:
            for motor in att["attenuator"].motors.values():
                motor.motion_hooks.append(FeMotionHook(frontend))

    @property
    def name(self):
        return self.__name

    def _find_index(self, attenuator_name):
        """Find the index of the attenuator in the list of attenuators.
        Args:
            (str): attenuator name
        Returns:
            (int): attenuator index
        """
        for attenuator in self.attenuators:
            if attenuator["attenuator"].name == attenuator_name:
                return self.attenuators.index(attenuator)
        return None

    def find_home_size(self, motor, step=None):
        """Procedure to find the size of the filter - home switch is active.
           Move the motor until the home switch is no more active.
        Args:
            motor (Axis): axis object.
            step (float): step size to use when search for the home switch end.
        """
        state = motor.state
        # check if the home switch is active
        if "HOME" in state and "LIMNEG" in state:
            print("Negative limit and home switch at the same place")
            b_home = motor.position
        else:
            # move the axis to the home switch active
            print(" - Searching home switch")
            motor.home(1)
            b_home = motor.position

        step = step or 10 / motor.steps_per_unit
        print(" - Move until home switch not active")
        while "HOME" in motor.state:
            motor.rmove(step)
        e_home = motor.position
        print(f"Home switch found at {b_home}, left at {e_home}")
        return abs(b_home - e_home)

    def find_configuration(self, attenuator_name):
        """Initialisation procedure:
             Find the negative limit switch.
             Find all the filters by home switch search
        Args:
            (str): attenuator name configured as multiple position axis.
        """
        idx = self._find_index(attenuator_name)
        motor = self.attenuators[idx]["attenuator"].motor_objs[0]
        new_position = {}

        print(" - Searching negative limit switch")
        motor.hw_limit(-1)
        motor.position = 0
        motor.dial = 0

        for pos in self.attenuators[idx]["attenuator"].positions_list:
            size = self.find_home_size(motor)
            motor.rmove(-size / 2)
            new_position[pos["label"]] = motor.position
            print(
                f"Move to the middle of the {pos['label']}: {new_position[pos['label']]}"
            )
        return new_position

    def update_configuration(self, att_name, new_positions):
        """Update already existing positions for a given attenuator
        Args:
            (str): attenuator name configured as multiple position axis.
            (dict): label:position
        """
        idx = self._find_index(att_name)
        att = self.attenuators[idx]["attenuator"]

        for lbl, pos in new_positions.items():
            att.update_position(lbl, [(att.motor_objs[0], pos)])

    @property
    def state(self):
        """Read the state"""
        msg = ""
        for att in self.attenuators:
            msg += f'{att["attenuator"].name}: {att["attenuator"].state} '
        return msg

    def __info__(self):
        """Return the exhaustive status of the object.
        Returns:
            (str): The status as string
        """
        info_str = ""
        for att in self.attenuators:
            att_name = att["attenuator"].name
            info_str += f"Attenuator: '{att_name}'\n"
            info_str += att["attenuator"].__info__()[:-1]  # remove trailing '\n'

            for motor in att["attenuator"].motors.values():
                if "HOME" in motor.state:
                    info_str += f" is in HOME position\n"
                else:
                    index = info_str.rfind("\n")
                    info_str = (
                        info_str[: index + 1]
                        + f" WARNING:"
                        + info_str[index + 1 :]
                        + " not in HOME position\n"
                    )

            info_str += "\n"
        return info_str

    @property
    def position(self):
        """Read the position of the attenuators.
        Returns:
            (list): atteuator, position for all the attenuators.
        """
        pos = []
        for att in self.attenuators:
            pos += [att["attenuator"].name, att["attenuator"].position]
        return pos

    def move(self, *att_name_pos_list, wait=True):
        """Move attenuator(s) to given position. The attenuators are moved
           simultaneously.
        Args:
            att_name_pos_list(list): two elements per attenuator: (name or
                                     attenuator object, position)
            wait(bool): wait until the end of move. Default value is True.
        """

        if len(att_name_pos_list) == 1:
            # assuming is a list or tuple
            att_name_pos_list = att_name_pos_list[0]

        # start moving all the attenuators
        for arg_in, pos in grouped(att_name_pos_list, 2):
            attenuator = self._get_attenuator(arg_in)

            for motor_obj in attenuator.motors.values():
                # add hook
                motor_obj.motion_hooks.insert(0, CheckHook(motor_obj))

            attenuator.move(pos, wait=False)

        # wait the end of the move
        if wait:
            self.wait(att_name_pos_list)

    def _get_attenuator(self, arg_in):
        if hasattr(arg_in, "name"):
            name = arg_in.name
        elif isinstance(arg_in, str):
            name = arg_in
        else:
            raise RuntimeError("Provide a valid attenuator object or name")

        idx = self._find_index(name)
        if idx is None:
            raise RuntimeError(
                "The provided attenuator was not found in the configuration"
            )

        return self.attenuators[idx]["attenuator"]

    def wait(self, *att_name_pos_list):
        """ Wait until the end of move finished
        Args:

            att_name_pos_list(list): two elements per attenuator: (name or
                                     attenuator object, position)
        """
        if len(att_name_pos_list) == 1:
            # assuming is a list or tuple
            att_name_pos_list = att_name_pos_list[0]

        for name, _ in grouped(att_name_pos_list, 2):
            self._get_attenuator(name).wait()


class WhiteBeamAttenuatorMockup(WhiteBeamAttenuator):
    def __init__(self, name, config, *args, **kwargs):
        self.faulty = config.pop("faulty", False)
        super().__init__(name, config, *args, **kwargs)
        for att in self.attenuators:
            for motor in att["attenuator"].motors.values():
                if self.faulty:
                    if "HOME" in motor.state:
                        motor.controller._hw_state.unset("HOME")  # start move from home
                else:
                    motor.controller._hw_state.set("HOME")  # start move from home

    def move(self, *args, **kwargs):

        for att in self.attenuators:
            for axis in att["attenuator"].motors.values():
                wait = kwargs.pop("wait", True)
                super().move(*args, **kwargs, wait=False)
                if wait:
                    super().wait(*args, **kwargs)
