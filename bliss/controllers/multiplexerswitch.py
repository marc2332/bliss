# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import global_map
from bliss.common.logtools import log_debug
from bliss.common.switch import Switch


class MultiplexerSwitch(Switch):
    def _init(self):
        try:
            self.__mux_ctrl = self.config.get("mux_controller")
        except RuntimeError:
            raise ValueError(
                "Invalid mux_controller in multiplexer switch {0}".format(self.name)
            )
        self.__mux_name = self.config.get("mux_name")

    def _initialize_hardware(self):
        try:
            self.__states_list = self.__mux_ctrl.getPossibleValues(self.__mux_name)
        except KeyError:
            raise KeyError(
                "Invalid mux_name {0} in multiplexer switch {1}".format(
                    self.__mux_name, self.name
                )
            )

    def _states_list(self):
        return self.__states_list

    def _set(self, state):
        self.__mux_ctrl.switch(self.__mux_name, state)

    def _get(self):
        return self.__mux_ctrl.getOutputStat(self.__mux_name)

    @Switch.lazy_init
    def __info__(self):
        infos = "Multiplexer     : {0}\n".format(self.__mux_ctrl.name)
        infos += "Possible states : {0}\n".format(self.states_list())
        infos += "Current state   : {0}\n".format(self.get())
        return infos
