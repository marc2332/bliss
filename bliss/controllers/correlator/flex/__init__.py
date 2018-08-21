# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Flex Correlator

Minimalistic configuration example:

.. code-block:: yaml

   plugin: bliss
   module: correlator.flex
   name: flex
   class: Flex
   address: tcp://lid312:8909
"""
from bliss.comm import rpc
from . import counters
from .card import MODE


class Flex:
    MODE = MODE

    def __init__(self, name, config):
        kwargs = dict()
        if "timeout" in config:
            kwargs["timeout"] = config["timeout"]
        self._proxy = rpc.Client(config["address"], **kwargs)

    @property
    def name(self):
        return self._proxy.name

    @property
    def counters(self):
        return counters.get_counters(self)

    @property
    def mode(self):
        return self._proxy.mode

    def start_acquisition(self):
        return self._proxy.start_acquisition()

    def stop_acquisition(self):
        return self._proxy.stop_acquisition()

    @property
    def intensities_and_acqtime(self):
        return self._proxy.intensities_and_acqtime

    @property
    def trace(self):
        return self._proxy.trace

    @property
    def data(self):
        return self._proxy.data
