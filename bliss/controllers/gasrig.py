# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Gasrig controller (used in ESRF ID15 and ID31 beamlines).
Consists of:
- N keller pressure transmitters (0 < N < 2)
- wago PLC with up to 13 valves and a (optional)
- massflow reader (optional)

As a convention the wago logical-names for the valves are 'pN' (where N > 0).


YAML_ configuration example:

.. code-block:: yaml

    - name: gasrig1
      module: gasrig
      class: GasRig
      wago: $wago_gasrig
      kellers:
      - $keller1              # optional keller(s)
      mks_wago_counter: qh2   # optional MKS 910 wago counter

    - name: keller1
      module: keller
      class: PressureTransmitter
      serial:
        url: enet://hexstarbis:50000/dev/ttyUSB0
      serial_nb: 133445
      counters:
      - counter_name: k1p
        type: P1
      - counter_name: k1t
        type: T1
    - name: keller2
      module: keller
      class: PressureTransmitter
      serial:
        url: enet://hexstarbis:50000/dev/ttyUSB1
      serial_nb: 544331
      counters:
      - counter_name: k2p
        type: P1
      - counter_name: k2t
        type: T1

    - name: wago_gasrig
      class: wago
      controller_ip: 160.103.51.39
      mapping:
      - type: 750-530
        logical_names: p1,p2,p3,p4,p5,p6,p7,p8
      - type: 750-530
        logical_names: p9,p10,p11,p12,p13,pso,wcdm2c7,wcdm2c8
      - type: 750-422
        logical_names: wcdm3c1,wcdm3c2,wcdm3c3,wcdm3c4
      - type: 750-478
        logical_names: preact,wcdm5c2
      - type: 750-478
        logical_names: qargon,qh2
      - type: 750-517
        logical_names: wcdm4c1,wcdm4c2
      - type: 750-469
        logical_names: wcdtk1,wcdtk2
      - type: 750-469
        logical_names: wcdts1,wcdts2
      # if you defined a mks_wago_counter it needs to be here:
      counter_names: qargon, qh2


Example usage:

    $ bliss
    >>> gasrig1 = config.get('gasrig1')
    >>> from bliss.common.scans import timescan
    >>> timescan(0.1, gasrig1.k1_t, gasrig1.k1_p npoints=10)

    Scan 24 Tue Sep 19 11:04:19 2017 /tmp/scans/slits/ slits user = coutinho
    timescan 0.1

           #         dt(s)    k1_t(degC)     k1_p(bar)
           0      0.017508        25.978    -0.0121813
           1      0.118953        25.978    -0.0123425
           2      0.220274        25.978    -0.0126181
           3      0.321995        25.978    -0.0128341
           4      0.423533        25.978    -0.0126414
           5      0.524867        25.978    -0.0123582
           6      0.626358        25.978    -0.0125952
           7      0.728253        25.978    -0.0126686
           8      0.829707        26.002    -0.0127244
           9      0.931273        26.002    -0.0126653

    Took 0:00:01.074992

    >>> gasrig1.open_valve(1)
    >>> gasrig1.close_all_valves()
"""

import logging
import functools

from bliss.controllers.wago import WagoCounter


def _get_wago_channel_names(wago, name_filter=None):
    if name_filter is None:
        name_filter = lambda x: True
    if wago.controller is None:
        wago.connect()
    channels = []
    for module in wago.controller.mapping:
        channels.extend(filter(name_filter, module["channels"][1]))
    return channels


def _get_gasrig_valve_names(wago):
    def filt(n):
        if not n.startswith("p"):
            return False
        try:
            int(n[1:])
            return True
        except ValueError:
            return False

    return _get_wago_channel_names(wago, name_filter=filt)


class MKS910Counter(WagoCounter):
    def __init__(self, wago_counter):
        WagoCounter.__init__(
            self,
            wago_counter.cntname,
            wago_counter.parent,
            index=wago_counter.index,
            conversion_function=MKS910Counter.adc_to_mbar,
        )

    @staticmethod
    def adc_to_mbar(adcval):
        return 10 ** (adcval - 6.0) * 1.33322368


class GasRig(object):
    """
    Gasrig controller
    """

    def __init__(self, name, config):
        self.config = config
        self.name = name
        self._log = logging.getLogger("{0}.{1}".format(self.__class__.__name__, name))
        wago = config["wago"]
        self.valve_names = set(_get_gasrig_valve_names(wago))
        for counter in wago.counters:
            if hasattr(self, counter.cntname):
                self._log.error(
                    "Skipped gasrig wago counter %r (controller "
                    "already has a member with that name)",
                    counter.cntname,
                )
                continue
            if config.get("mks_wago_counter") == counter.cntname:
                counter = MKS910Counter(counter)
            setattr(self, counter.cntname, counter)

        for keller in self.config["kellers"]:
            for name, counter in keller.counters.items():
                if hasattr(self, counter.name):
                    self._log.error(
                        "Skipped gasrig keller counter %r "
                        "(controller already has a member with "
                        "that name)",
                        name,
                    )
                    continue
                setattr(self, name, counter)

    def _set_valve(self, valve, value=0):
        if "p" + str(valve) not in self.valve_names:
            raise ValueError("Unknown valve {0!r}".format(valve))
        self.wago.set("p{0}".format(valve), value)

    open_valve = functools.partial(_set_valve, value=1)
    close_valve = functools.partial(_set_valve, value=0)

    def close_all_valves(self):
        valves = self.valve_names
        self.wago.set(*zip(valves, len(valves) * (0,)))

    def open_all_valves(self):
        valves = self.valve_names
        self.wago.set(*zip(valves, len(valves) * (1,)))
