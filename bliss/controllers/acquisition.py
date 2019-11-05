# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import namedtuple


def counter_namespace(counters):
    if isinstance(counters, dict):
        dct = counters
    else:
        dct = {counter.name: counter for counter in counters}
    return namedtuple("namespace", sorted(dct))(**dct)


class CounterController:
    def __init__(
        self, name, master_controller=None, chain_node_class=None, hw_ctrl=None
    ):
        super().__init__()
        self.__name = name
        self._chain_node_class = chain_node_class
        self._master_controller = master_controller
        self._counters = {}

    @property
    def name(self):
        return self.__name

    @property
    def master_controller(self):
        return self._master_controller

    @property
    def counters(self):
        return counter_namespace(self._counters)

    def create_chain_node(self):
        if self._chain_node_class is None:
            raise NotImplementedError
        else:
            return self._chain_node_class(self)

    def apply_parameters(self, ctrl_params):
        pass

    #### needed by grouped read...
    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    ####
