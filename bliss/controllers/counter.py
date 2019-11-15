# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import namedtuple
import numpy
from bliss import global_map
from bliss.common.counter import Counter, CalcCounter
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

    def add_counter(self, counter):
        self._counters[counter.name] = counter

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
    def __init__(self, name, config):

        super().__init__(name, chain_node_class=CalcCounterChainNode)

        self._input_counters = []
        self._output_counters = []
        self._counters = {}
        self.tags = {}

        # === reset by self.prepare() ================
        self.data = {}
        self.data_index = {}
        self.emitted_index = -1

        self.build_counters(config)

    def build_counters(self, config):
        """ Build the CalcCounters from config. 
            'config' is a dict with 2 keys: 'inputs' and 'outputs'.
            'config["inputs"]'  is a list of dict:  [{"counter":$cnt1, "tags": foo }, ...]
            'config["outputs"]' is a list of dict:  [{"name":out1, "tags": calc_data_1 }, ...]
            If the 'tags' is not found, the counter name will be used instead.
        """
        for cnt_conf in config.get("inputs"):

            cnt = cnt_conf.get("counter")
            if isinstance(cnt, Counter):
                tags = cnt_conf.get("tags", cnt.name)
                self.tags[cnt.name] = tags
                self._input_counters.append(cnt)
            else:
                raise RuntimeError(
                    f"CalcCounterController inputs must be a counter but received: {cnt}"
                )

        for cnt_conf in config.get("outputs"):

            cnt_name = cnt_conf.get("name")
            if cnt_name:
                cnt = CalcCounter(cnt_name, self)
                tags = cnt_conf.get("tags", cnt.name)
                self.tags[cnt.name] = tags
                self._output_counters.append(cnt)

    @property
    def inputs(self):
        return self._input_counters

    @property
    def outputs(self):
        return self._output_counters

    @property
    def counters(self):
        """ return all counters (i.e. the counters of this CounterController and sub counters) """

        counters = {cnt.name: cnt for cnt in self._output_counters}
        for cnt in self._input_counters:
            counters[cnt.name] = cnt
            if isinstance(cnt, CalcCounter):
                counters.update({cnt.name: cnt for cnt in cnt.controller.counters})
        return counter_namespace(counters)

    def compute(self, sender, data_dict):
        """
        This method works only if all input_counters will generate the same number of points !!!
        It registers all data comming from the input counters.
        It calls calc_function with input counters data which have reach the same index
        This function is called once per counter (input and output).

        * <sender> = AcquisitionChannel 
        * <data_dict> = {'em1ch1': array([0.00256367])}
        """

        for cnt in self._input_counters:
            # get registered data for this counter
            data = self.data.get(cnt.name, [])

            # get new data for this counter
            new_data = data_dict.get(cnt.name, [])

            # get number of registered data for this counter
            data_index = self.data_index.get(cnt.name, 0)

            # If any, add new data to registered data
            if len(new_data):
                data = numpy.append(data, new_data)
                self.data[cnt.name] = data

            self.data_index[cnt.name] = data_index + len(new_data)

        input_counter_index = [
            self.data_index[cnt.name] for cnt in self._input_counters
        ]
        new_data_index = min(input_counter_index)

        # print(f"\n{self.name} - {new_data_index} - {input_counter_index}")

        if self.emitted_index == new_data_index - 1:
            return None

        # Build a dict of input counter data value indexed by tags instead of counter names.
        input_data_dict = {}
        for cnt in self._input_counters:
            input_data_dict[self.tags[cnt.name]] = numpy.copy(
                self.data[cnt.name][self.emitted_index + 1 : new_data_index]
            )

        self.emitted_index = new_data_index - 1

        output_data_dict = self.calc_function(input_data_dict)

        return output_data_dict

    def prepare(self):
        # Store read input counter datas
        self.data = {}
        # last index of read input counter datas
        self.data_index = {}
        # index of last calculated counter datas
        self.emitted_index = -1

    def start(self):
        pass

    def stop(self):
        pass

    def calc_function(self, input_dict):
        raise NotImplementedError


class SoftCounterController(SamplingCounterController):
    def __init__(self, name="soft_counter_controller"):
        super().__init__(name)

    def read(self, counter):
        return counter.apply(counter.get_value())
