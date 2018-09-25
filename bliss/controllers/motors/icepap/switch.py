# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
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
        self.__axes = weakref.WeakValueDictionary()
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
            for axis in self.__controller._axes.values():
                # be sure that axis is initialized
                try:
                    axis.position()
                except (RuntimeError, KeyError):
                    continue
                try:
                    include_rack.add(axis.address // 10)
                except (AttributeError, TypeError):  # LinkedAxis and TrajectoryAxis
                    continue
        else:
            include_rack = set(include_rack)

        exclude_rack = config.get("exclude-rack")
        if exclude_rack is None:
            exclude_rack = set()
        else:
            exclude_rack = set(exclude_rack)

        managed_rack = include_rack - exclude_rack
        self.__axes = weakref.WeakValueDictionary()
        for axis_name, axis in self.__controller._axes.iteritems():
            try:
                rack_id = axis.address // 10
            except (AttributeError, TypeError):
                continue
            if rack_id in managed_rack:
                self.__axes[axis_name.upper()] = axis

    def _set(self, state):
        cnx = self.__controller._cnx
        if state is None or state == "DISABLED":
            _command(cnx, "PMUX REMOVE E%d" % self.__rack_connector_id)
            return

        axis = self.__axes.get(state)
        if axis is None:
            raise ValueError(
                "State %s does't exist in the switch %s" % (state, self.name)
            )

        _command(cnx, "PMUX REMOVE E%d" % self.__rack_connector_id)
        _ackcommand(cnx, "PMUX HARD B%d E%d" % (axis.address, self.__rack_connector_id))
        _ackcommand(cnx, "%d:SYNCPOS %s" % (axis.address, self.__syncpos_type))

    def _get(self):
        reply = _command(self.__controller._cnx, "?PMUX")
        pattern = re.compile(".+B([0-9]+) +E%d" % self.__rack_connector_id)
        for line in reply.split("\n"):
            m = pattern.match(line)
            if m:
                axis_address = int(m.group(1))
                for axis_name, axis in self.__axes.iteritems():
                    if axis.address == axis_address:
                        return axis_name
        return "DISABLED"

    def _states_list(self):
        return self.__axes.keys() + ["DISABLED"]
