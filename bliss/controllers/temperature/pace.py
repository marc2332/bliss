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
name: 
class: pace
url: 'id29pace1:5025' #host:port
outputs:
    - name: pmb_press
      channel: 1            # for 6000 only
"""

# import for Controller
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop
import random
import time
import math
from bliss.common import log

from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set


# import for this controller
from bliss.comm.tcp import Tcp
import logging
import time

class pace(Controller):

    def __init__(self, config, *args):

        Controller.__init__(self, config, *args)
 
        if "timeout" in config:
            self.timeout = config["timeout"]
        else:
            self.timeout = 3
            
        if "url" in config:
            self._sock = Tcp(config["url"], timeout=self.timeout)
        else:
            raise RuntimeError("pace: should give a communication url")
        
        self.units={1:"MBAR", 2:"BAR", 3:"PA", 4:"HPA", 5:"KPA",
                    12: "KG/M2", 19:"TORR", 20:"ATM"}
            
        #check if the device replies correctly
        reply = self._sock.write_readline("*IDN?\r", eol="\r", timeout=self.timeout)
        
        if "PACE" in reply:
            model = reply.split(",")[1]
        else:
            model = str(self)
        self._logger = logging.getLogger("%s" % model)
        self._logger.setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.INFO)

    def initialize(self):
        pass

    def initialize_output(self, toutput):
        pass

    def __del__(self):
        self._sock.close()


    def set(self, toutput, pressure):
        """Controller method:
           Setting a setpoint as quickly as possible

           TO BE REVIEWED: need to disable the ramp before

           Set the pressure setpoint
        Args:
           pressure (float): Pressure setpoint value
        Returns:
           None
        """
        try:
            self._send_comm(":SOUR%1d:PRES %f"%(toutput.channel, pressure))
        except RuntimeError:
            self._logger.error("Pressure not set")


    def start_ramp(self, toutput, pressure, **kwargs):
        """Controller method:
           Doing a ramp on a Output object

           Change the pressure to a set value at a controlled rate
           Args:
              rate (float): ramp rate in current units per second
              pressure (float): target pressure
           Returns:
              (float, float): current ramp rate , target pressure        
        """
        if kwargs.has_key("ramp"):
           toutput.rampval(kwargs["ramp"])

        self._ramprate(toutput.rampval())

        try:
            self._send_comm(":SOUR%1d:PRES %f"%(toutput.channel, pressure))
        except RuntimeError:
            self._logger.error("Pressure not set")


    def get_setpoint(self,toutput):
        """Controller method:
           Get the setpoint value on a Output object

        Returned value is None if not setpoint is set
        """
        try:
            return float(self._query_comm(":SOUR%1d:PRES?"%(toutput.channel)))
        except ValueError:
            self._logger.error("Pressure not read")

    def read_output(self,toutput):
        """Controller method:
           Reading on a TOutput object
        Returned value is None if not setpoint is set

        """
        return self._read_pressure(toutput.channel)

        
    def _read_pressure(self,channel):
        """Read the current pressure
        Returns:
           (float): The pressure in the current units
        """
        try:
            return float(self._query_comm(":SENS%1d:PRES?"%channel))
        except ValueError:
            self._logger.error("Cannot read the pressure")


    def _ramprate(self, rate=None):
        """Set/Read the rate the controller should use to acieve setpoint
        Args:
            rate (float): Desired rate in pressure inits per second
        Returns:
            (float): Current rate in selected pressure inits per second
        """
        channel = 1
        if rate:
            try:
               self._send_comm("SOUR%1d:PRES:SLEW %f" % (channel, rate))
            except RuntimeError:
                self._logger.error("Slew rate not set")
        else:
            try:
                return self._query_comm("SOUR%1d:PRES:SLEW?" % channel)
            except ValueError:
                self._logger.error("Cannot read the current slew rate")    
        
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
