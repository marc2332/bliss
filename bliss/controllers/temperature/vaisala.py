# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Vaisala temperature controller

So far only the HMT330 is supported.
"""

from bliss.controllers import vaisala
from bliss.controllers.temp import Controller


class HMT330(Controller):
    """
    Vaisala HUMICAP(r) temperature controller for series HMT330

    Recommended setup: On the device display configure the following:

    - serial line: baudrate: 9600 data bits:8 parity:N stop bits: 1
      flow control: None
    - serial mode: STOP
    - echo: OFF
    - no date
    - no time
    - metric unit

    Example of YAML configuration:

    .. code-block:: yaml

        plugin: temperature
        module: vaisala
        class: HMT330
        serial:
          url: ser2net://lid312:29000/dev/ttyRP20
        inputs:
        - name: temp1
          channel: T               # (1)
        - name: humidity1
          channel: RH              # (1)

    * (1) `channel` is any accepted HMT330 abbreviation quantities.
      Main quantities: 'RH', 'T'.
      Optional: 'TDF', 'TD', 'A', 'X', 'TW', 'H2O', 'PW', 'PWS', 'H', 'DT'
    """

    def initialize(self):
        config = dict(self.config)
        config["counters"] = counters = []
        for inp_cfg in self.config.get("inputs", ()):
            inp_cfg["counter name"] = inp_cfg["name"]
            counters.append(inp_cfg)
        name = config.setdefault("name", "hmt330")
        self.dev = vaisala.HMT330(name, config)

    def read_input(self, tinput):
        channel = tinput.config["channel"]
        return self.dev[channel]
