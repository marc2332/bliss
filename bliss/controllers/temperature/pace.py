# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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
       channel: 1            # for 6000 only
"""

""" TempController import """
from bliss.controllers.temp import Controller
from bliss.common.temperature import Output
from bliss.common import log
from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set

# import for this controller
from bliss.comm.tcp import Tcp
import logging

class Pace:
    def __init__(self, url=None, timeout=3, debug=False):
        self.timeout = timeout
        self._sock = Tcp(url, timeout=self.timeout)
        self.units={1:"MBAR", 2:"BAR", 3:"PA", 4:"HPA", 5:"KPA",
                    12: "KG/M2", 19:"TORR", 20:"ATM"}

    def __del__(self):
        self._sock.close()

    def exit(self):
        self._sock.close()

    def init(self):
        #check if the device replies correctly
        reply = self._sock.write_readline("*IDN?\r", eol="\r", timeout=self.timeout)
        
        if "PACE" in reply:
            model = reply.split(",")[1]
        else:
            model = str(self)
        self._logger = logging.getLogger("%s" % model)
        self._logger.setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.INFO)

    def setpoint(self, pressure=None, channel=1):
        """Set/Read the pressure setpoint
        Args:
           pressure (float): Pressure setpoint value
        Returns:
           pressure(float): Current setpoint value
        """
        if pressure:
            try:
                self._send_comm(":SOUR%1d:PRES %f"%(channel, pressure))
            except RuntimeError:
                self._logger.error("Pressure not set")
        else:
            try:
                return float(self._query_comm(":SOUR%1d:PRES?"%(channel)))
            except ValueError:
                self._logger.error("Pressure setpoint not read")

    def ramp(self, pressure=None, rate=None, channel=1):
        """Start ramping to the pressure setpoint/Get current ramp parameters
        Args:
           pressure (float): target pressure
           rate (float): ramp rate in current units per second
        Returns:
           (float, float): target pressure, current ramp rate
        """
        if ramp:
            self.ramprate(ramp, channel)
        else:
            ramp = self.ramprate()

        if pressure:
            self.setpoint(pressure, channel)
        else:
            pressure = setpoint(pressure, channel)

        return (pressure, ramp)

    def ramprate(self, rate=None, channel=1):
        """Set/Read the rate the controller should use to achieve setpoint
        Args:
            rate (float): Desired rate in pressure units per second
        Returns:
            (float): Current rate in selected pressure units per second
        """
        if rate:
            try:
               self._send_comm("SOUR%1d:PRES:SLEW %f" % (channel, rate))
            except RuntimeError:
                self._logger.error("Ramp rate not set")
        else:
            try:
                return self._query_comm("SOUR%1d:PRES:SLEW?" % channel)
            except ValueError:
                self._logger.error("Cannot read the current ramp rate")

    def read_pressure(self,channel=1):
        """Read the current pressure
        Returns:
           (float): The pressure in the current units
        """
        try:
            return float(self._query_comm(":SENS%1d:PRES?"%channel))
        except ValueError:
            self._logger.error("Cannot read the pressure")
        
    def _unit(self, unit=None):
        """Set/Read the pressure unit
        Args:
           (int): Desired unit as int the units dictionary
        Returns:
           (string): The pressure in the current units
        """
        if unit:
            try:
                self._send_comm(":UNIT%1d:PRES %s"%(self,channel, self.units[unit]))
            except Exception, err:
                self._logger.error("Cannot set the pressure unit")
            

        else:
            try:
                return self._query_comm(":UNIT%1d:PRES?"%self,channel)
            except ValueError:
                self._logger.error("Cannot read the current pressure unit")
    
    def _query_comm(self, msg):
        """Send a query command. Read the reply
        Args:
           msg (string): The query command, which should end with ?
        Returns:
           (string): The reply
              False: when invalid reply
        """
        if not msg.endswith("?"):
           self._logger.error("Invalid command %s" % msg)
        else:
            self._logger.debug("Command %s" % msg)
            reply = self._sock.write_readline(msg+'\r', eol="\r", timeout=self.timeout)
            try:
                _,val = reply.split()
                return val.strip("\r")
            except (ValueError,AttributeError), e:
                self._logger.error(e)
                return False

    def _read_error(self):
        """Check for an error
           Returns:
              (string): Error string if error
                 False: Wneh no error
        """
        reply = self._sock.write_readline("SYST:ERR?"+'\r', eol="\r", timeout=self.timeout)
        if not "No error" in reply:
            return reply.split(",")[1]
        return False

    def _send_comm(self, msg):
        """Send a command.
        Args:
           msg (string): The comamnd
        Returns:
           None
        """
        self._logger.debug("Command %s" % msg)
        self._sock.write(msg+'\r')
        err = self._read_error()
        if err:
            self._logger.error(err)
            raise RuntimeError(err)


class pace(Controller):
    def __init__(self, config, *args):
        if not "url" in config:
            raise RuntimeError("pace: should give a communication url")

        self._pace = Pace(config["url"], config.get("timeout"))

        Controller.__init__(self, config, *args)

    def initialize(self):
        self._pace.init()

    def initialize_output(self, toutput):
        self.__ramp_rate = None
        self.__set_point = None
        self.channel = toutput.config.get("channel") or 1

    def __del__(self):
        self._pace.exit()

    def start_ramp(self, toutput, sp, **kwargs):
        """ Send the command to start ramping to a setpoint.
        Args:
           toutput (object): Output class type object
           sp (float): setpoint
           **kwargs: auxilliary arguments:
              rate (float): ramp rate in current units per second
	Raises:
	   RuntimeError: the ramp rate is not set
        """
        try:
            rate = int(kwargs.get("rate", self.__ramp_rate))
        except TypeError:
            raise RuntimeError("Cannot start ramping, ramp rate not set")

        self._pace.ramp(pressure, rate, self.channel)

    def set_ramprate(self, toutput, rate, **kwargs):
        """ Set the ramp rate.
         Args:
            toutput (object): Output class type object
            rate (float): Desired rate in pressure units per second
        """
        self.__ramp_rate = rate
        toutput.rampval(rate)
        self._pace.ramprate(rate, self.channel)

    def read_ramprate(self, toutput):
        """ Read the ramp rate.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): Current rate in selected pressure units per second
                    None if no ramp rate set
        """
        self.__ramp_rate = self._pace.ramprate(None, self.channel)
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

    def get_setpoint(self,toutput):
        """ Get the setpoint value.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): Current setpoint in selected pressure units
                    None if no setpoint set
        """
        self.__set_point = self._pace.setpoint(None, self.channel)
        return self.__set_point

    def read_output(self,toutput):
        """ Read the pressure.
        Args:
           toutput (object): Output class type object
        Returns:
           (float): The pressure in the current units
        """
        return self._pace.read_pressure(self.channel)

    def state_output(self,toutput):
        """ Read the state.
        Args:
           toutput(object): Output class type object
        Returns:
           (string): The controller state
        """
        return "READY"


if __name__ == '__main__':
    _pace = Pace('id29pace1:5025')

    _pace.init()

    print _pace.read_pressure()
