# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Vacuum gauge controller.

example yml file:
-
  # pirani gauge
  plugin: bliss
  name: pir121
  class: VacuumGauge
  uri: id43/v-pir/121

-
  # penning gauge
  plugin: bliss
  name: pen121
  class: VacuumGauge
  uri: id43/v-balzpen/121

test examples:

RH [1]: pir121.state
Out [1]: 'ON'


CYRIL [2]: pen71
  Out [2]:
           ----------------  id42/v-pen/71 ---------------
           State: ON
           Gauge is ON  -  Channel A1 (1)
           Rel. | Lower | Upper | SA | State
             1  | 1.5e-6| 5.0e-6|  1 |  ON
             2  | 4.0e-3| 6.0e-3|  2 |  ON
             3  | 1.0e-6| 3.0e-6|  3 |  ON
             4  | 4.0e-3| 6.0e-3|  4 |  ON
             A  | 4.0e-3| 1.0e-5|  6 |  ON
             B  | 4.0e-3| 1.0e-5|  8 |  ON

           Failed to connect to device sys/hdb-push/id42
           The connection request was delayed.
           The last connection request was done less than 1000 ms ago
           -------------------------------------------------
           PRESSURE: 2.30e-07
           -------------------------------------------------

RH [3]: pir121.pressure
Out [3]: 0.0007999999797903001
"""

from bliss import global_map
from bliss.common.tango import DeviceProxy, DevFailed


class VacuumGauge:
    def __init__(self, name, config):
        tango_uri = config.get("uri")
        self.__name = name
        self.__config = config
        self.__control = DeviceProxy(tango_uri)
        global_map.register(
            self, children_list=[self.__control], tag=f"VacuumGauge:{name}"
        )

    @property
    def name(self):
        """A unique name"""
        return self.__name

    @property
    def config(self):
        """Config of vg"""
        return self.__config

    @property
    def proxy(self):
        return self.__control

    @property
    def _tango_state(self):
        """ Read the tango state. (class tango.DevState) Available PyTango states:
            'ALARM', 'CLOSE', 'DISABLE', 'EXTRACT', 'FAULT', 'INIT', 'INSERT',
            'MOVING', 'OFF', 'ON', 'OPEN', 'RUNNING', 'STANDBY', 'UNKNOWN'.
        Returns:
            (str): The state from the device server.
        """
        return self.__control.state().name

    @property
    def _tango_status(self):
        """ Read the status.
        Returns:
            (str): Complete state from the device server.
        """
        return self.__control.status()

    @property
    def state(self):
        try:
            state = self._tango_state
            return state
        except DevFailed:
            raise RuntimeError(f"Communication error with {self.__control.dev_name()}")

    @property
    def status(self):
        """Return state as combined string
        Returns
            state as string + tango status
        """
        _status = f"State: {self.state}{self._tango_status}"
        return _status

    def __info__(self):
        info_str = f" \n----------------  {self.proxy.dev_name()} ---------------\n"
        info_str += self.status.rstrip("\n") + "\n"
        info_str += "-------------------------------------------------\n"
        info_str += f"PRESSURE: {self.pressure:1.2e}\n"
        info_str += "-------------------------------------------------\n"
        return info_str

    @property
    def pressure(self):
        return self.__control.pressure

    def set_on(self):
        self.__control.On()

    def set_off(self):
        self.__control.Off()

    def reset(self):
        """Reset
        Args:
        Raises:
            RuntimeError: Cannot execute
        """
        self.__control.Reset()
