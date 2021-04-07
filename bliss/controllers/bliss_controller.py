# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from time import perf_counter, sleep
from itertools import chain
from collections import ChainMap

from bliss import global_map
from bliss.common.protocols import CounterContainer
from bliss.common.counter import Counter, CalcCounter
from bliss.common.protocols import counter_namespace
from bliss.common.utils import autocomplete_property
from bliss.comm.util import get_comm

from bliss.config.beacon_object import BeaconObject

from bliss.common.logtools import log_info, log_debug, log_debug_data, log_warning


class HardwareController:
    def __init__(self, config):
        self._config = config

        self._last_cmd_time = perf_counter()
        self._cmd_min_delta_time = 0

        self._comm = get_comm(config)

        global_map.register(self._comm, parents_list=[self, "comms"])

    @property
    def config(self):
        return self._config

    @property
    def comm(self):
        return self._comm

    def send_cmd(self, cmd, values):
        if self._cmd_min_delta_time:
            delta_t = perf_counter() - self._last_cmd_time
            if delta_t < self._cmd_min_delta_time:
                sleep(self._cmd_min_delta_time - delta_t)
            
        return self._send_cmd(cmd, *values)

    def _send_cmd(self, cmd, *values):
        if values:
            return self._write_cmd(cmd, *values)
        else:
            return self._read_cmd(cmd)

    def _write_cmd(self, cmd, *values):
        # return self._comm.write(cmd, *values)
        raise NotImplementedError

    def _read_cmd(self, cmd):
        # return self._comm.read(cmd)
        raise NotImplementedError


class BlissController(CounterContainer):

    def __init__(self, name, config):

        self._name = name
        self._config = config

        self._counter_controllers = []
        self._hw_controller = None

        self._load_config(config)
        self._build_axes()
        self._build_counters()

    def _initialize_hardware(self):
        """ Must return an HardwareController object """
        raise NotImplementedError

    def _load_config(self):
        """ Read and apply the YML configuration """
        raise NotImplementedError

    def _build_counters(self):
        """ Build the CounterControllers and associated Counters"""
        raise NotImplementedError

    def _build_axes(self):
        """ Build the Axes (real and pseudo) """
        raise NotImplementedError

    @autocomplete_property
    def hw_controller(self):
        if self._hw_controller is None:
            self._hw_controller = self._initialize_hardware()
        return self._hw_controller

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    @property
    def counters(self):
        # cnts = [ctrl.counters for ctrl in self._counter_controllers]
        # return counter_namespace(chain(*cnts))
        raise NotImplementedError


    @property
    def axes(self):
        # axes = [ctrl.axes for ctrl in self._axis_controllers]
        # return dict(ChainMap(*axes))
        raise NotImplementedError


class TopController:
    def __init__(self, name, config):
        self._name = name
        self._config = config

        self._bliss_controllers = []

        self._load_config(config)

    def _load_config(self):
        """ Read and apply the YML configuration """
        raise NotImplementedError

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    @property
    def counters(self):
        cnts = [ctrl.counters for ctrl in self._bliss_controllers]
        return counter_namespace(chain(*cnts))

    @property
    def axes(self):
        axes = [ctrl.axes for ctrl in self._bliss_controllers]
        return counter_namespace(chain(*axes))




