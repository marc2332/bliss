# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Flex Correlator

Minimalistic configuration example:

.. code-block:: yaml

   plugin: bliss
   module: correlator.flex
   name: flex
   class: Flex
   #address: tcp://lid312:8909
   taco_url: id10/flex/2
   taco_db_host: ting           # optional 
"""
from bliss import global_map
from bliss.comm.taco.client import Client
from . import counters
from .card import MODE


class Flex:
    MODE = MODE

    def __init__(self, name, config):
        self._name = name
        self._proxy = Client(config["taco_url"], config.get("taco_db_host"))
        global_map.register(self, parents_list=["counters", "controllers"])

    @property
    def name(self):
        return self._name

    @property
    def fullname(self):
        return self.name

    @property
    def counters(self):
        return counters.get_counters(self)

    @property
    def mode(self):
        return MODE(self._proxy.DevFlexGetMode())

    @mode.setter
    def mode(self, mo):
        self._proxy.DevFlexSetMode(mo.value)

    def start_acquisition(self):
        return self._proxy.DevFlexStart()

    def stop_acquisition(self):
        return self._proxy.DevFlexStop()

    @property
    def intensities_and_acqtime(self):
        return self._proxy.DevFlexGetInt()

    @property
    def trace(self):
        return self._proxy.trace

    @property
    def data(self):
        data = self._proxy.DevFlexReadData()
        mode = self.mode
        if mode == MODE.SINGLE_AUTO or mode == MODE.SINGLE_CROSS:
            data.shape = 2, -1
        elif mode == MODE.DUAL_AUTO or mode == MODE.DUAL_CROSS:
            data.shape = 3, -1
        elif mode == MODE.QUAD:
            data.shape = 5, -1
        return data

    def __info__(self):
        return f"Flex ({self.name}):\n\tmode: {self.mode}"
