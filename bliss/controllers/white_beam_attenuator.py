# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
from bliss.common.utils import grouped


class WhiteBeamAttenuator:
    """Methods to control White Beam Attenuator."""

    def __init__(self, name, config):
        self.attenuators = config.get("attenuators")
        self.__name = name
        global_map.register(self, tag=name)

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
        if state == state.HOME and state == state.LIMNEG:
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
            info_str += att["attenuator"].__info__()
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

    def move(self, att_name_pos_list, wait=True):
        """Move attenuator(s) to given position. The attenuators are moved
           simultaneously.
        Args:
            att_name_pos_list(list): two elements per attenuator: name, position
            wait(bool): wait until the end of move. Default value is True.
        """
        # start moving all the attenuators
        for name, pos in grouped(att_name_pos_list, 2):
            idx = self._find_index(name)
            self.attenuators[idx]["attenuator"].move(pos, wait=False)

        # wait the end of the move
        if wait:
            self.wait(att_name_pos_list)

    def wait(self, att_name_pos_list):
        """ Wait until the end of move finished
        Args:
            att_name_pos_list(list): list of attenuators name, position.
        """
        for name, _ in grouped(att_name_pos_list, 2):
            idx = self._find_index(name)
            self.attenuators[idx]["attenuator"].wait()
