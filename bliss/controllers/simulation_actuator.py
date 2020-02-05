# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


class SimulationActuator:
    def __init__(self):
        self.__in = False
        self.__out = False

    def set(self, cmd, arg):
        if cmd == "set_in":
            self.__in = bool(arg)
            self.__out = not self.__in
        if cmd == "set_out":
            self.__out = bool(arg)
            self.__in = not self.__out

    def get(self, cmd):
        return self.__in if cmd == "set_in" else self.__out
