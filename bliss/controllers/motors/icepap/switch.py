# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import weakref
import re

from bliss.common.switch import Switch as BaseSwitch
from . import _ackcommand, _command


class Switch(BaseSwitch):
    """
    Switch for IcePAP DB9 front panel output.
    Basic configuration:
        name: ice_switch0
        include-rack: [1,2,3,4]   # if not specify all rack will be included
        exclude-rack: [5]
        external-connector-id: 3 # i.e the 4th output. default is 0 (DB9 from Master)
        syncpos-type: MOTOR #i.e Axis electrical phase. default is MEASURE (Signal used as axis measurement)
    """

    def __init__(self, name, controller, config):
        BaseSwitch.__init__(self, name, config)
        self.__controller = weakref.proxy(controller)
        self.__addresses = dict()
        self.__rack_connector_id = None
        self.__syncpos_type = None

    def _init(self):
        config = self.config
        self.__rack_connector_id = config.get("external-connector-id", 0)
        syncpos_type = config.get("syncpos-type", "MEASURE").upper()
        possible_type = (
            "AXIS",
            "MOTOR",
            "MEASURE",
            "SHFTENC",
            "TGTENC",
            "CTRLENC",
            "ENCIN",
            "INPOS",
            "ABSENC",
        )
        if syncpos_type not in possible_type:
            raise ValueError("syncpos-type can only be: %s" % possible_type)
        self.__syncpos_type = syncpos_type
        include_rack = config.get("include-rack")
        if include_rack is None:  # All
            include_rack = set()
            for axis_class, axis_config in self.__controller._axes_config.values():
                address = axis_config.get("address", None)
                if not isinstance(address, int):
                    continue
                include_rack.add(address // 10)
        else:
            include_rack = set(include_rack)

        exclude_rack = config.get("exclude-rack")
        if exclude_rack is None:
            exclude_rack = set()
        else:
            exclude_rack = set(exclude_rack)

        managed_rack = include_rack - exclude_rack
        self.__addresses = dict()
        for (
            axis_name,
            (axis_class, axis_config),
        ) in self.__controller._axes_config.items():
            address = axis_config.get("address", None)
            if not isinstance(address, int):
                continue
            rack_id = address // 10
            if rack_id in managed_rack:
                self.__addresses[axis_name.upper()] = address

    def _set(self, state):
        cnx = self.__controller._cnx
        if state is None or state == "DISABLED":
            _command(cnx, "PMUX REMOVE E%d" % self.__rack_connector_id)
            return

        address = self.__addresses.get(state)
        if address is None:
            raise ValueError(
                "State %s does't exist in the switch %s" % (state, self.name)
            )

        _command(cnx, "PMUX REMOVE E%d" % self.__rack_connector_id)
        _ackcommand(cnx, "PMUX HARD B%d E%d" % (address, self.__rack_connector_id))
        _ackcommand(cnx, "%d:SYNCPOS %s" % (address, self.__syncpos_type))

    def _get(self):
        reply = _command(self.__controller._cnx, "?PMUX")
        pattern = re.compile(r".+B([0-9]+) +E%d" % self.__rack_connector_id)
        for line in reply.split("\n"):
            m = pattern.match(line)
            if m:
                axis_address = int(m.group(1))
                for axis_name, address in self.__addresses.items():
                    if address == axis_address:
                        return axis_name
        return "DISABLED"

    def _states_list(self):
        return list(self.__addresses.keys()) + ["DISABLED"]

    def pmux_state(self):
        reply = _command(self.__controller._cnx, "?PMUX")
        return reply.split("\r\n")

    def pmux_reset(self, rackid=None):
        cnx = self.__controller._cnx
        if rackid is None:
            _ackcommand(cnx, "PMUX REMOVE")
            self.set("DISABLED")
        elif rackid == self.__rack_connector_id:
            self.set("DISABLED")
        else:
            _ackcommand(cnx, "PMUX REMOVE E%d" % rackid)
