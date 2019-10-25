# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import namedtuple

from bliss import global_map
from bliss.common.counter import CalcCounter
from bliss.scanning.acquisition.counter import SamplingChainNode
from bliss.scanning.acquisition.counter import IntegratingChainNode
from bliss.scanning.acquisition.calc import CalcCounterChainNode


def counter_namespace(counters):
    if isinstance(counters, dict):
        dct = counters
    else:
        dct = {counter.name: counter for counter in counters}
    return namedtuple("namespace", dct)(**dct)


class CounterController:
    def __init__(
        self, name, master_controller=None, chain_node_class=None
    ):  # , hw_ctrl=None):

        self.__name = name
        self._chain_node_class = chain_node_class
        self._master_controller = master_controller
        self._counters = {}

        # self._hw_controller = hw_ctrl

        global_map.register(self, parents_list=["controllers"])

    @property
    def name(self):
        return self.__name

    @property
    def fullname(self):
        if self.master_controller is None:
            return self.name
        else:
            return f"{self.master_controller.fullname}:{self.name}"

    @property
    def master_controller(self):
        return self._master_controller

    # @property
    # def hw_controller(self):
    #     return self._hw_controller

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

    def prepare(self, *counters):
        pass

    def start(self, *counters):
        pass

    def stop(self, *counters):
        pass


class SamplingCounterController(CounterController):
    def __init__(
        self,
        name="sampling_counter_controller",
        master_controller=None,
        chain_node_class=SamplingChainNode,
    ):
        super().__init__(
            name, master_controller=master_controller, chain_node_class=chain_node_class
        )

    def read_all(self, *counters):
        """ return the values of the given counters as a list.
            If possible this method should optimize the reading of all counters at once.
        """
        values = []
        for cnt in counters:
            values.append(self.read(cnt))
        return values

    def read(self, counter):
        """ return the value of the given counter """
        raise NotImplementedError


class IntegratingCounterController(CounterController):
    def __init__(
        self,
        name="integrating_counter_controller",
        master_controller=None,
        chain_node_class=IntegratingChainNode,
    ):
        super().__init__(
            name, master_controller=master_controller, chain_node_class=chain_node_class
        )

    def get_values(self, from_index, *counters):
        raise NotImplementedError


class CalcCounterController(CounterController):
    def __init__(self, name, calc_function, *dependent_counters):
        super().__init__(
            "calc_counter_controller", chain_node_class=CalcCounterChainNode
        )
        self.__dependent_counters = dependent_counters
        self.__counter = CalcCounter(name, self, calc_function)
        global_map.register(self.__counter, ["counters"], tag=name)

    @property
    def calc_counter(self):
        return self.__counter

    @property
    def counters(self):
        self._counters = {self.__counter.name: self.__counter}

        for cnt in self.__dependent_counters:
            if isinstance(cnt, CalcCounter):
                self._counters.update(
                    {cnt.name: cnt for cnt in cnt.controller.counters}
                )
            else:
                self._counters[cnt.name] = cnt
        return counter_namespace(self._counters)


class SoftCounterController(SamplingCounterController):
    def __init__(self, name="soft_counter_controller"):
        super().__init__(name)

    def read(self, counter):
        return counter.apply(counter.get_value())
