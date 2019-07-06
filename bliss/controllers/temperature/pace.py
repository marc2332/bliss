# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PACE (Pressure Automated Calibration Equipmet) , acessible via tcp sockets
5000 and 6000 models

Only one channel to control
yml configuration example:
controller:
   class: pace
   url: 'id29pace1:5025' #host:port
   outputs:
     - name: pmbpress
       low_limit: 0
       high_limit: 2.1
       default_unit: 'BAR'
       channel: 1            # for 6000 only
"""
# temperature controller
from bliss.controllers.temp import Controller
from bliss.common.temperature import Output
from bliss.common.utils import object_attribute_type_get
from bliss.common.utils import object_attribute_type_set
from bliss.common.logtools import *
from bliss.common import session

# communication
from bliss.comm.tcp import Tcp


class Pace:
    def __init__(self, url=None, timeout=3):
        self.timeout = timeout
        self._units = ("ATM", "BAR", "MBAR", "PA", "HPA", "KPA", "MPA", "TORR", "KG/M2")
        self._eol = "\r"

        self._sock = Tcp(url, timeout=timeout)

        session.get_current().map.register(
            self, parents_list=["comms"], children_list=[self._sock], tag="Pace:{url}"
        )

    def close(self):
        self._sock.close()

    def init(self):
        """ Read the ID of the module. Set the logger.
        """
        resp = self.putget("*IDN?")
        # check if the device replies correctly
        if "PACE" in resp:
            model = resp.split(",")[1]
        else:
            model = str(self)

    def _mode(self, channel=1, mode=None):
        """Set/Read the rate the controller should achieve set-point.
           Args:
              channel (int): channel number (default 1)
              mode (str): mode - MAX (maximum rate)
                            LIN (user selected linear rate)
          Returns:
              (str): current rate mode
        """
        cmd = "SOUR%1d:SLEW:MODE" % channel
        if mode:
            try:
                self._send_comm(cmd + " %s" % mode.upper())
            except RuntimeError as e:
                log_error(self, "Mode not set: " + str(e))
        else:
            try:
                return self._query_comm(cmd)
            except Exception as e:
                log_error(self, "Mode not read: " + str(e))

    def _setpoint(self, channel=1, pressure=None):
        """Set/Read the pressure set-point
        Args:
           channel (int): channel number (default 1)
           pressure (float): Pressure setpoint value
        Returns:
           (float): Current pressure set-point value.
        """
        cmd = ":SOUR%1d:PRES" % channel
        if pressure:
            try:
                self._send_comm(cmd + " %f" % pressure)
            except RuntimeError as e:
                log_error(self, "Pressure set-point not set: " + str(e))
        else:
            try:
                return float(self._query_comm(cmd))
            except Exception as e:
                log_error(self, "Pressure set-point not read: " + str(e))

    def _ramprate(self, channel=1, rate=None):
        """Set/Read the rate the controller should use to achieve setpoint
        Args:
            channel (int): channel number (default 1)
            rate (float): Desired rate in pressure units per second - optional
        Returns:
            (float): Current rate in selected pressure units per second
        """
        cmd = "SOUR%1d:PRES:SLEW" % channel
        if rate:
            try:
                self._send_comm(cmd + " %f" % rate)
            except RuntimeError as e:
                log_error(self, "Ramp rate not set: " + str(e))
        else:
            try:
                return self._query_comm(cmd)
            except Exception as e:
                log_error(self, "Cannot read the current ramp rate: " + str(e))

    def _unit(self, channel=1, unit=None):
        """Set/Read the pressure unit
        Args:
           channel (int): Desired unit as int the units dictionary
           unit (str): Unit to be used
        Returns:
           (string): The pressure in the current units
        """
        cmd = ":UNIT%1d:PRES" % channel
        if unit:
            if unit.upper() in self._units:
                try:
                    self._send_comm(cmd + " %s" % unit)
                except RuntimeError as e:
                    log_error(self, "Cannot set the pressure unit: %s" % str(e))
            else:
                msg = "Cannot set the pressure unit: wrong input"
                log_error(self, msg)
                raise (msg)
        else:
            try:
                return self._query_comm(cmd)
            except Exception as e:
                log_error(self, "Cannot read the current pressure unit: " + str(e))

    def setpoint(self, pressure, channel=1):
        """Set the pressure to a value at maximum speed
        Args:
           pressure (float): Pressure set-point value
           channel (int): channel number (default 1)
        """
        try:
            self._mode(channel, "MAX")
            self._setpoint(channel, pressure)
        except Exception as e:
            log_error(self, "setpoint: " + str(e))

    def ramp(self, pressure=None, rate=None, channel=1):
        """Start ramping to the pressure setpoint
        Args:
           pressure (float): target pressure
           rate (float): ramp rate in current units per second
           channel (int): channel number (default 1)
        Returns:
           tupple(float, float): target pressure, current ramp rate
        """
        try:
            self._ramprate(channel, rate)
            self._mode(channel, "LIN")
            self._setpoint(channel, pressure)
        except RuntimeError as e:
            log_error(self, "ramp: " + str(e))

    def read_ramp(self, channel=1):
        """Read the current ramping parameters
        Args:
           channel (int): channel number (default 1)
        Returns:
           tupple(float, float): target pressure, current ramp rate
        """
        try:
            return (self._setpoint(channel), self._ramprate(channel))
        except Exception as e:
            log_error(self, str(e))

    def read_pressure(self, channel=1):
        """Read the current pressure
        Args:
           channel (int): channel mumber (default 1)
        Returns:
           (float): The pressure in the current units
        """
        cmd = ":SENS%1d:PRES" % channel
        try:
            return float(self._query_comm(cmd))
        except Exception as e:
            log_error(self, "Cannot read the pressure:" + str(e))

    def putget(self, cmd):
        """Send a command. Read the responce
        Args:
           cmd (string): The command
        Returns:
           (string): The responce
        """

        cmd += "\r"
        return self._sock.write_readline(
            cmd.encode(), eol=self._eol, timeout=self.timeout
        ).decode()

    def _query_comm(self, cmd):
        """Send a query command. Read the responce
        Args:
           cmd (string): The query command, which should end with ?
        Returns:
           (string): The responce
        """
        if not cmd.endswith("?"):
            cmd += "?"

        resp = self.putget(cmd)

        log_debug(self, "Command %s" % cmd)
        try:
            _, val = resp.split()
            return val.strip(self._eol)
        except (ValueError, AttributeError) as e:
            log_error(self, str(e))
            raise (e)

    def _read_error(self):
        """Check for an error
           Returns:
              (string): Error string if error
        """
        resp = self.putget("SYST:ERR?")
        if "No error" not in resp:
            return resp.split(",")[1]

    def _send_comm(self, cmd):
        """Send a command.
        Args:
           cmd (string): The comamnd
        """
        log_debug(self, "Command %s" % cmd)
        cmd += self._eol
        self._sock.write(cmd.encode())
        err = self._read_error()
        if err:
            log_error(self, err)
            raise RuntimeError(err)


class pace(Controller):
    def __init__(self, config, *args):
        if "url" not in config:
            raise RuntimeError("pace: should give a communication url")

        self._pace = Pace(config["url"], config.get("timeout"))

        super().__init__(config, *args)

        session.get_current().map.register(self, children_list=[self._pace])

    def initialize(self):
        self._pace.init()

    def initialize_output(self, toutput):
        self.__ramp_rate = None
        self.__set_point = None
        # set the default channel
        self.channel = toutput.config.get("channel") or 1
        # set the default pressure unit
        self.unit = toutput.config.get("default_unit") or "BAR"
        self.set_units(self.channel, self.unit)

    def close(self):
        self._pace.close()

    def start_ramp(self, toutput, sp, **kwargs):
        """ Send the command to start ramping to a setpoint.
        Args:
           toutput (object): Output class type object
           sp (float): pressure set-point
        Kwargs:
           rate (float): ramp rate in current units per second
        Raises:
           RuntimeError: the ramp rate is not set
        """
        try:
            rate = int(kwargs.get("rate", self.__ramp_rate))
        except TypeError:
            raise RuntimeError("Cannot start ramping, ramp rate not set")

        self._pace.ramp(self.channel, sp, rate)

    def set_ramprate(self, toutput, rate, **kwargs):
        """ Set the ramp rate.
         Args:
            toutput (object): Output class type object
            rate (float): Desired rate in pressure units per second
        """
        self.__ramp_rate = rate
        toutput.rampval(rate)
        self._pace._ramprate(self.channel, rate)

    def read_ramprate(self, toutput):
        """ Read the ramp rate.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): Current rate in selected pressure units per second
                    None if no ramp rate set
        """
        self.__ramp_rate = self._pace._ramprate(self.channel)
        return self.__ramp_rate

    def set(self, toutput, sp, **kwargs):
        """ Set the pressure setpoint (go as quick as possible).
        Args:
           toutput (object): Output class type object
           sp (float): Pressure setpoint value
        Returns:
           None
        """
        self._pace.setpoint(sp, self.channel)

    def get_setpoint(self, toutput):
        """ Get the setpoint value.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): Current setpoint in selected pressure units
                    None if no setpoint set
        """
        self.__set_point = self._pace.setpoint(self.channel)
        return self.__set_point

    def read_output(self, toutput):
        """ Read the pressure.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): The pressure in the current units
        """
        return self._pace.read_pressure(self.channel)

    def state_output(self, toutput):
        """ Read the state.
        Args:
           toutput(object): Output class type object
        Returns:
           (string): The controller state
        """
        return "READY"

    @object_attribute_type_get(type_info=("str"), type=Output)
    def get_units(self, toutput):
        """ Read the current units
        Args:
           toutput (object): Output class type object
        Returns:
           (string): The current pressure units
        """
        return self._pace._unit(self.channel)

    @object_attribute_type_set(type_info=("str"), type=Output)
    def set_units(self, toutput, unit):
        """ Read the current units
        Args:
           toutput (object): Output class type object
        Returns:
           (string): The current pressure units
        """
        return self._pace._unit(self.channel, unit)


if __name__ == "__main__":
    _pace = Pace("id29pace1:5025")

    _pace.init()

    print(_pace.read_pressure())
