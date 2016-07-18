# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PACE (Pressure Automated Calibration Equipmet) , acessible via tcp sockets
5000 and 6000 models

yml configuration example:
name: 
class: pace
url: 'id29pace1:5025' #host:port
channel: 0            # for 6000 only
"""

from bliss.comm.tcp import Tcp
import logging
import time

class pace:

    def __init__(self, name, config):

        self._setpoint = None
        if "timeout" in config:
            self.timeout = config["timeout"]
        else:
            self.timeout = 3
            
        if "url" in config:
            self._sock = Tcp(config["url"], timeout=self.timeout)
        else:
            raise RuntimeError("pace: should give a communication url")
        
        if "channel" in config:
            self.channel = int(config["channel"])
        else:
            self.channel = 1

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

    def __del__(self):
        self._sock.close()

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
        reply = self._query_comm("SYST:ERR?")
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
        err = self.read_error()
        if err:
            self._logger.error(err)
            raise RuntimeError(err)
        
        
    def setpoint(self, pressure):
        """Set the pressure setpoint
        Args:
           pressure (float): Pressure setpoint value
        Returns:
           None
        """
        try:
            self._send_comm(":SOUR%1d:PRES %f"%(self,channel, pressure))
            self._setpoint = pressure
        except RuntimeError:
            self._logger.error("Pressure not set")


    def ramp(self, rate=None, pressure=None):
        """Change the pressure to a set value at a controlled rate
           Args:
              rate (float): ramp rate in current units per second
              pressure (float): target pressure
           Returns:
              (float, float): current ramp rate , target pressure
        """
        if rate and pressure:
            self._ramprate(rate)
            self.setpoint(pressure)
        else:
            _rate = self._ramprate()
            return (_rate, self._setpoint)
        
    def read_pressure(self):
        """Read the current pressure
        Returns:
           (float): The pressure in the current units
        """
        try:
            return float(self._query_comm(":SENS%1d:PRES?"%self,channel))
        except ValueError:
            self._logger.error("Cannot read the pressure")


    def _ramprate(self, rate=None):
        """Set/Read the rate the controller should use to acieve setpoint
        Args:
            rate (float): Desired rate in pressure inits per second
        Returns:
            (float): Current rate in selected pressure inits per second
        """
        if rate:
            try:
               self._send_comm("SOUR%1d:PRES:SLEW %f" % (self,channel, rate))
            except RuntimeError:
                self._logger.error("Slew rate not set")
        else:
            try:
                return self._query_comm("SOUR%1d:PRES:SLEW?" % self,channel)
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
    
            
