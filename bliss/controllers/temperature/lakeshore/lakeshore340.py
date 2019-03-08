# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 340, acessible via GPIB, Serial line or Ethernet

yml configuration example:
controller:
   class: lakeshore340
   eos: '\r\n'
   timeout: 3
#gpib
   gpib:
      url: id30oh3ls335  #enet://gpibid30b1.esrf.fr
      pad: 12
#serial line
   serial:
      url: "rfc2217://lidxxx:28003"
      baudrate: 57600
#ethernet
   tcp:
      url: idxxlakeshore:7777
   inputs:
       -
        name: ls335_A
        channel: A # or B
        #tango_server: ls_335
   outputs:
       -
        name: ls335o_1
        channel: 1 #  to 4
        units: K  #K(elvin) C(elsius) S(ensor)
   ctrl_loops:
       -
        name: ls335l_1
        input: $ls335_A
        output: $ls335o_1
        channel: 1 # to 4
"""


import time
import os
import re

# from bliss.common import log
import logging

# communication
from bliss.comm.tcp import Tcp
from bliss.comm.gpib import Gpib
from bliss.comm import serial

from bliss.controllers.temperature.lakeshore.lakeshore import Base


class LakeShore340(object):

    MODE340 = (
        "Off",
        "Manual PID",
        "Zone",
        "Open Loop",
        "Auto Tune PID",
        "Auto Tune PI",
        "Auto Tune P",
    )

    UNITS340 = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS340 = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    CURVEFORMAT340 = {
        1: "mV/K",
        2: "V/K",
        3: "Ohms/K",
        4: "logOhms/K",
        5: "logOhms/logK",
    }
    CURVETEMPCOEF340 = {1: "negative", 2: "positive"}

    def __init__(self, comm_type, url, **kwargs):
        self.eos = kwargs.get("eos", "\r\n")
        timeout = kwargs.get("timeout", 0.5)
        if "gpib" in comm_type:
            self._comm = Gpib(
                url, pad=kwargs["extra_param"], eos=self.eos, timeout=timeout
            )
        elif ("serial" or "usb") in comm_type:
            baudrate = kwargs.get("extra_param", 9600)
            self._comm = serial.Serial(
                url,
                baudrate=baudrate,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                eol=self.eos,
            )
        elif "tcp" in comm_type:
            self._comm = Tcp(url, eol=self.eos, timeout=timeout)
        else:
            return RuntimeError("Unknown communication  protocol")
        self._channel = None
        self.log = logging.getLogger(type(self).__name__)
        # self.log.setLevel(logging.NOTSET)
        self.log.setLevel(logging.DEBUG)
        self.log.debug("__init__")

    def _initialize_loop(self, loop):
        self._add_custom_method_loop(loop)

    def _initialize_output(self, output):
        self._add_custom_method_output(output)

    def _initialize_input(self, input):
        self._add_custom_method_input(input)

    def _add_custom_method_loop(self, loop):
        def cset(input=None, units=None, onoff=None):
            """ Read/Set Control Loop Parameters
                Args:
                   input (str): which input to control from. Valid entries: A or B.
                   units (str): sensor unit. Valid entries: Kelvin, Celsius, sensor unit.
                   onoff (str): control loop is on or off. Valid entries are on or off.
              Returns:
                   None if set
                   input (str): which input control the loop.
                   units (str): Unit for the input: Kelvin, Celsius, sensor unit.
                   onoff (str): control loop: on  or off.
            """
            return self._cset(
                loop.config.get("channel"), input=input, units=units, onoff=onoff
            )

        loop.cset = cset

        def cmode(mode=None):
            """ Read/Set Control Loop Mode
                Args:
                   mode (int): control mode. Valid entries: 1=Manual PID,
                               2=Zone, 3=Open Loop, 4=AutoTune PID,
                               5=AutoTune PI, 6=AutoTune P
                Returns:
                   None if set
                   mode (int): mode
            """
            return self._cmode(loop.config.get("channel"), mode=mode)

        loop.cmode = cmode

        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        loop.model = model

        def show():
            """  Display all main parameters and values for the temperature controller
                Returns:
                  model, PID, heater range, loop status, sensors configuration,
                  inputs temperature
            """
            return self._show()

        loop.show = show

    def _add_custom_method_output(self, output):
        def ramp_status():
            """Check ramp status (if running or not)
               Args:
                  None
                Returns:
                  Ramp status (1 = running, 0 = not running)
            """
            return self._rampstatus(output.config.get("channel"))

        output.ramp_status = ramp_status

        def heater_range(value=None):
            """ Set/Read the heater range (0 to 5) from 0 to 50W in 50Ohms
                Args:
                  value (int): The value of the range if set
                           None if read
                Returns:
                  None if set
                  value (int): The value of the range if read
            """
            return self._heater_range(output.config.get("channel"), value=value)

        output.heater_range = heater_range

        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        output.model = model

        def show():
            """  Display all main parameters and values for the temperature controller
                Returns:
                  model, PID, heater range, loop status, sensors configuration,
                  inputs temperature
            """
            return self._show()

        output.show = show

    def _add_custom_method_input(self, input):
        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        input.model = model

        def curve_used_curve():
            """ Get the input curve used
                Print:
                   curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
                   curve name (str): limited to 15 characters
                   curve SN (str): limited to 10 characters (Standard,...)
                   curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
                   curve temperature limit (float): in Kelvin
                   curve temperature coefficient (int): 1=negative, 2=positive
            """

            return self._curve_used_curve(input.config.get("channel"))

        input.curve_used_curve = curve_used_curve

        def curve_list_all():
            """ List all the curves
                Returns:
                  a row for all the curves from 1 to 60
            """
            return self._curve_list_all()

        input.curve_list_all = curve_list_all

        def curve_write(crvn=None, crvfile=None):
            """ Write the user curve into the Lakeshore
                Args:
                  crvn (int): The user curve number from 21 to 60
                  crvfile (str): full file name
                Returns:
                  Status of curve written
            """
            return self._curve_write(crvn, crvfile)

        input.curve_write = curve_write

        def curve_delete(crvn=None):
            """ Delete a user curve from the Lakeshore
                Args:
                  crvn (int): The user curve number from 21 to 60
                Returns:
                  None.
            """
            self._curve_delete(crvn)

        input.curve_delete = curve_delete

        def show():
            """  Display all main parameters and values for the temperature controller
                Returns:
                  model, PID, heater range, loop status, sensors configuration,
                  inputs temperature
            """
            return self._show()

        input.show = show

        def filter(onoff=None, points=None, window=None):
            """  Configure input filter parameters
                Args:
                   onoff (int): 1 = enable, 0 = disable
                   points (int): specifies how the filtering fct uses
                   window (int): specifies what percent of full scale reading
                                 limits the filtering function. Reading changes
                                 greater than this percentage reset the filter.
                Returns:
                  None
            """
            return self._filter(
                input.config.get("channel"), onoff=onoff, points=points, window=window
            )

        input.filter = filter

    def clear(self):
        """Clears the bits in the Status Byte, Standard Event and Operation
           Event Registers. Terminates all pending operations.
           Returns:
              None
        """
        # see if this should not be removed
        self.send_cmd("*CLS")

    def read_temperature(self, channel):
        """ Read the current temperature
            Args:
              channel (int): input channel. Valid entries: A or B
            Returns:
              (float): current temperature [K]
        """
        self._channel = channel
        return float(self.send_cmd("KRDG?"))

    def _model(self):
        """ Get the model number
            Returns:
              model (int): model number
        """
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:])

    def _show(self):
        """ Display all main parameters and values for the 
            temperature controller
            Returns:
              device ID, PID, heater range, loop status, 
              sensors configuration, inputs temperature etc.
        """

        # Get full identification string
        full_id = self.send_cmd("*IDN?")
        print("\nLakeshore identification %s" % (full_id))

        # Sensor A
        # --------
        print("\nSensor A:")
        print("=========")

        # Get temperature calibration curve
        asw = self.send_cmd("INCRV? A")
        print("Uses calibration curve number %d" % int(asw))
        asw = self.send_cmd("CRVHDR? %s" % asw)
        asw = asw.split(",")
        print(
            "Curve type = %s, SerNum = %s, Format = %s"
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT340[int(asw[2])])
        )
        print(
            "Temp.limit = %s K , Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF340[int(asw[4])])
        )

        # Read input temperature and resistance
        temp_A = float(self.send_cmd("KRDG? A"))
        resist_A = float(self.send_cmd("SRDG? A"))
        print("Current Temperature = %.3f Resistance = %.3f" % (temp_A, resist_A))

        # Sensor B
        # --------
        print("\nSensor B:")
        print("=========")

        # Get temperature calibration curve
        asw = self.send_cmd("INCRV? B")
        print("Uses calibration curve number %d" % int(asw))
        asw = self.send_cmd("CRVHDR? %s" % asw)
        asw = asw.split(",")
        print(
            "Curve type = %s, SerNum = %s, Format = %s"
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT340[int(asw[2])])
        )
        print(
            "Temp.limit = %s K, Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF340[int(asw[4])])
        )

        # Read input temperature and resistance
        temp_B = float(self.send_cmd("KRDG? B"))
        resist_B = float(self.send_cmd("SRDG? B"))
        print("Current Temperature = %.3f Resistance = %.3f" % (temp_B, resist_B))

        # Loop 1
        # ------
        print("\nLoop 1:")
        print("=======")

        # Get control loop parameters
        asw = self.send_cmd("CSET? 1").split(",")
        sensor = asw[0]
        units = self.REVUNITS340[int(asw[1])]
        onoff = "ON" if bool(int(asw[2])) else "OFF"
        print("Controlled by sensor %s in %s and is %s." % (sensor, units, onoff))

        # Read ramp enable/disable status and ramp rate
        rp_1 = self.send_cmd("RAMP? 1").split(",")
        ronoff_1 = "ON" if int(rp_1[0]) == 1 else "OFF"
        rrate_1 = float(rp_1[1])

        # Read setpoint
        sp_1 = float(self.send_cmd("SETP? 1"))

        print(
            "Ramp enable is %s with set-point %.3f %s and ramp-rate = %.3f K/min."
            % (ronoff_1, sp_1, units, rrate_1)
        )
        # Read ramp status (only if ramp is enabled)
        if ronoff_1 == "ON":
            asw = self.send_cmd("RAMPST? 1")
            rs_1 = "RAMPING" if int(asw) == 1 else "NOT RAMPING"
            print("Ramp status is %s." % rs_1)

        # Get control loop mode
        asw = self.send_cmd("CMODE? 1")
        print("Temp Control is set to %s" % self.MODE340[int(asw)])

        kp, ki, kd = self.send_cmd("PID? 1").split(",")
        print("PID parameters: ")
        print("     P = %.1f" % float(kp))
        print("     I = %.1f" % float(ki))
        print("     D = %.1f" % float(kd))

        # Loop 2
        # ------
        print("\nLoop 2:")
        print("=======")

        # Get control loop parameters
        asw = self.send_cmd("CSET? 2").split(",")
        sensor = asw[0]
        units = self.REVUNITS340[int(asw[1])]
        onoff = "ON" if bool(int(asw[2])) else "OFF"
        print("Controlled by sensor %s in %s and is %s." % (sensor, units, onoff))

        # Read ramp enable/disable status and ramp rate
        rp_2 = self.send_cmd("RAMP? 2").split(",")
        ronoff_2 = "ON" if int(rp_2[0]) == 1 else "OFF"
        rrate_2 = float(rp_2[1])

        # Read setpoint
        sp_2 = float(self.send_cmd("SETP? 2"))

        print(
            "Ramp enable is %s with set-point %.3f %s and ramp-rate = %.3f K/min. "
            % (ronoff_2, sp_2, units, rrate_2)
        )
        # Read ramp status (only if ramp is enabled)
        if ronoff_2 == "ON":
            asw = self.send_cmd("RAMPST? 2")
            rs_2 = "RAMPING" if int(asw) == 1 else "NOT RAMPING"
            print("Ramp status is %s." % rs_2)

        # Get control loop mode
        asw = self.send_cmd("CMODE? 2")
        print("Temp Control is set to %s" % self.MODE340[int(asw)])

        # Get PID parameters for loop 2
        kp, ki, kd = self.send_cmd("PID? 2").split(",")
        print("PID parameters: ")
        print("     P = %.1f" % float(kp))
        print("     I = %.1f" % float(ki))
        print("     D = %.1f" % float(kd))

        # Heater
        # ------
        print("\nHeater:")
        print("=======")
        # Get heater range value
        htr_range = int(self.send_cmd("RANGE?"))
        if htr_range == 0:
            print("Heater is OFF")
        else:
            print("Heater is on range = %d" % htr_range)

    def _filter(self, channel, **kwargs):
        """  Configure input filter parameters
            Args:
               onoff (int): 1 = enable, 0 = disable
               points (int): specifies how the filtering fct uses
               window (int): specifies what percent of full scale reading
                             limits the filtering function. Reading changes
                             greater than this percentage reset the filter.
            Returns:
              None
        """
        self._channel = channel
        input = channel
        onoff = kwargs.get("onoff")
        points = kwargs.get("points")
        window = kwargs.get("window")

        if onoff is None and points is None and window is None:
            asw = self.send_cmd("FILTER?").split(",")
            onoff = int(asw[0])
            points = int(asw[1])
            window = int(asw[2])
            return (onoff, points, window)
        else:
            onoffc, pointsc, windowc = self.send_cmd("FILTER?").split(",")
            if onoff is None:
                onoff = onoffc
            if points is None:
                points = pointsc
            if window is None:
                window = windowc
            # TO DO find the true limits
            # elif window not in range(0,101):
            #     return print("Error: window acceptables values are [0,100].")

            self.send_cmd("FILTER", int(onoff), int(points), int(window))

    def _curve_used_curve(self, channel):
        """ Get the input curve used
            Print:
               curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
               curve name (str): limited to 15 characters
               curve SN (str): limited to 10 characters (Standard,...)
               curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
               curve temperature limit (float): in Kelvin
               curve temperature coefficient (int): 1=negative, 2=positive
        """
        self._channel = channel
        curve_number = self.send_cmd("INCRV?")
        command = "CRVHDR? %s" % curve_number
        curve_header = self.send_cmd(command)
        header = curve_header.split(",")
        curve_name = header[0]
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT340[int(header[2])]
        curve_temperature_limit = header[3]
        curve_temperature_coefficient = self.CURVETEMPCOEF340[int(header[4])]
        print(
            "curve name: %s\tcurve SN: %s\t format: %s\n\
temperature limit: %sK\t\ttemp. coefficient: %s"
            % (
                curve_name,
                curve_sn,
                curve_format,
                curve_temperature_limit,
                curve_temperature_coefficient,
            )
        )

    def _curve_list_all(self):
        """ Get the input curve used
            Print:
               curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
               curve name (str): limited to 15 characters
               curve SN (str): limited to 10 characters (Standard,...)
               curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
               curve temperature limit (float): in Kelvin
               curve temperature coefficient (int): 1=negative, 2=positive
        """
        # self._channel = channel

        # curve_number = self.send_cmd("INCRV?")
        print(" #            Name       SN         Format     Limit(K) Temp. coef.")
        for i in range(1, 61):
            command = "CRVHDR? %s" % i
            curve_header = self.send_cmd(command)
            header = curve_header.split(",")
            curve_name = header[0].strip()
            curve_sn = header[1]
            curve_format = self.CURVEFORMAT340[int(header[2])]
            curve_temperature_limit = header[3]
            curve_temperature_coefficient = self.CURVETEMPCOEF340[int(header[4])]
            print(
                "%2d %15s %10s %12s %12s %s"
                % (
                    i,
                    curve_name,
                    curve_sn,
                    curve_format,
                    curve_temperature_limit,
                    curve_temperature_coefficient,
                )
            )

    def _curve_write(self, crvn, crvfile):
        """ Write the user curve to the Lakeshore
            Args:
              crvn (int): The user curve number from 21 to 60
              crvfile (str): full file name
            Returns:
              Status of curve written
        """
        if crvn is None:
            crvn = input("Number of curve to be written [21,60]? ")
        else:
            print("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 61):
            raise ValueError("User curve number %d is not in [21,60]" % crvn)

        print("Readings from actual curve %d in LakeShore 340 :" % crvn)
        command = "CRVHDR? %d" % crvn
        loaded_curve = self.send_cmd(command)
        header = loaded_curve.split(",")
        curve_name = header[0].strip()
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT340[int(header[2])]
        curve_temp_limit = header[3]
        curve_temp_coeff = self.CURVETEMPCOEF340[int(header[4])]
        print("no channel")
        print(
            "\t%15s %10s %12s %12s %s"
            % (curve_name, curve_sn, curve_format, curve_temp_limit, curve_temp_coeff)
        )
        print("no channel")
        if crvfile is None:
            crvfile = input("Filename of temperature curve? ")
        else:
            print("File name passed as arg = %s" % crvfile)

        if os.path.isfile(crvfile) == False:
            raise FileNotFoundError("Curve file %s not found" % crvfile)

        with open(crvfile) as f:

            for line in f:
                # print(line)
                if line.count(":") == 1:
                    lline = line.split(":")
                    # print(lline[0] + lline[1])
                    if lline[0] == "Sensor Model":
                        curve_name = lline[1].strip()
                    if lline[0] == "Serial Number":
                        curve_sn = lline[1].strip()
                    if lline[0] == "Data Format":
                        curve_format_long = lline[1]
                        # cvf = curve_format_long.split(None,1)
                        # curve_format = cvf[0]
                        curve_format = curve_format_long.split(None, 1)[0]

                    if lline[0] == "SetPoint Limit":
                        curve_temp_limit_long = lline[1]
                        curve_temp_limit = curve_temp_limit_long.split(None, 1)[0]

                    if lline[0] == "Temperature coefficient":
                        curve_temp_coeff_long = lline[1]
                        curve_temp_coeff = curve_temp_coeff_long.split(None, 1)[0]

                    if lline[0] == "Number of Breakpoints":
                        curve_nb_breakpts = lline[1].strip()

            # checking header values
            if curve_name == "":
                raise ValueError("No sensor model")
            if curve_sn == "":
                raise ValueError("No serial number")
            if curve_format_long == "":
                raise ValueError("No data format")
            elif int(curve_format) not in range(1, 6):
                raise ValueError("Curve data format %s not in [1,5]" % curve_format)
            if curve_temp_limit_long == "":
                raise ValueError("No setpoint limit")
            if curve_temp_coeff_long == "":
                raise ValueError("No temperature coefficient")
            elif int(curve_temp_coeff) not in range(1, 3):
                raise ValueError(
                    "Curve temperature coefficient %s not in [1,2]" % curve_temp_coeff
                )
            if curve_nb_breakpts == "":
                raise ValueError("No number of breakpoints")
            elif int(curve_nb_breakpts) not in range(1, 201):
                raise ValueError(
                    "Number of breakpoints %s not in [1,200]" % curve_nb_breakpts
                )

        print("fichier ouvert et lu\n")

        print(curve_name)
        print(curve_sn)
        print(curve_format)
        print(curve_temp_limit)
        print(curve_temp_coeff)
        print(curve_nb_breakpts)

        # writing the curve header into the Lakeshore
        command = "CRVHDR %d,%s,%s,%d,%f,%d" % (
            crvn,
            curve_name,
            curve_sn,
            int(curve_format),
            float(curve_temp_limit),
            int(curve_temp_coeff),
        )
        # print(command)
        self.send_cmd(command)

        with open(crvfile) as f:
            for line in f:
                exp = re.compile(
                    r"^\s*([0-9]+)\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)\s*$"
                )
                if exp.match(line):
                    command = "CRVPT %d,%d,%f,%f" % (
                        crvn,
                        int(exp.match(line).group(1)),
                        float(exp.match(line).group(2)),
                        float(exp.match(line).group(3)),
                    )
                    print(command)
                    self.send_cmd(command)

        print(
            "Curve %d has been written into the LakeShore model 340 temperature controller."
            % crvn
        )

        # Reading back for checking the header
        command = "CRVHDR? %d" % crvn
        curve_header = self.send_cmd(command)
        print("The header read back for the %d is:" % crvn)
        print(curve_header)

        print(
            "Warning: The curve was not saved to the flash memory of the LakeShore 340."
        )
        answer = input("Do you want to save it into the curve flash memory ?")
        if answer.lower() == "yes" or answer.lower() == "y":
            print("This operation may take several seconds.")
            self.send_cmd("CRVSAV")
            print("The curve has been written into the flash memory.")

    def _curve_delete(self, crvn):
        """ Delete a user curve from the Lakeshore
            Args:
              crvn (int): The user curve number from 21 to 60
            Returns:
              None.
        """
        if crvn is None:
            crvn = input("Number of curve to be deleted [21,60]? ")
        else:
            print("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 61):
            raise ValueError("User curve number %d is not in [21,60]" % crvn)

        # Delete the curve
        command = "CRVDEL %d" % crvn
        self.send_cmd(command)

        print(
            "Warning: The curve was not deleted from the flash memory of the LakeShore 340."
        )
        answer = input("Do you want to delete the curve from the flash memory ?")
        if answer.lower() == "yes" or answer.lower() == "y":
            print("This operation may take several seconds.")
            self.send_cmd("CRVSAV")
            print("The curve has been deleted from the flash memory.")

    #########################################################

    def setpoint(self, channel, value=None):
        """ Set/Read the control setpoint
           Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (float): The value of the setpoint if set
                             None if read
           Returns:
              None if set
              value (float): The value of the setpoint if read
        """
        self._channel = channel
        if value is None:
            return float(self.send_cmd("SETP?"))
        # send the setpoint
        self.send_cmd("SETP", value)

    def _heater_range(self, channel, value=None):
        """ Set/Read the heater range (0=off 1=low 2=medium 3=high)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (int): The value of the range if set
                             None if read
           Returns:
              None if set
              value (int): The value of the range if read
        """
        self._channel = channel
        if value is None:
            return int(self.send_cmd("RANGE?"))
        # send the range
        if value not in [0, 1, 2, 3, 4, 5]:
            raise ValueError("Error, the value {0} is not in 0 to 5.".format(value))

        print("--------- value = {0}".format(value))
        self.send_cmd("RANGE", value)

    def ramp_rate(self, channel, value=None):
        """ Set/read the control setpoint ramp rate.
            Explicitly stop the ramping when setting.
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (float): The ramp rate [K/min] 0 to 100 with 0.1 resolution 
                             or None when reading.
           Returns:
              None if set
              value (float): The value of the ramp rate if read.
        """
        self._channel = channel
        if value is None:
            rate_value = self.send_cmd("RAMP?").split(",")[1]
            return float(rate_value)

        # send the ramp rate
        self.send_cmd("RAMP", 0, value)

    def ramp(self, channel, sp, rate):
        """Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self.log.debug("ramp(): SP=%r, RR=%r" % (sp, rate))
        self._channel = channel
        self.setpoint(channel, sp)
        self.send_cmd("RAMP", 1, rate)

    def _rampstatus(self, channel):
        """Check ramp status (if running or not)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
            Returns:
              Ramp status (1 = running, 0 = not running)
        """
        self.log.debug("_rampstatus(): channel = %r" % channel)
        self._channel = channel
        ramp_stat = self.send_cmd("RAMPST?")
        self.log.debug("_rampstatus(): ramp_status = %r" % ramp_stat)
        return int(ramp_stat)

    def pid(self, channel, **kwargs):
        """ Read/Set Control Loop PID Values (P, I, D)
           Args:
              channel (int): loop channel. Valid entries: 1 or 2
              P (float): Proportional gain (0.1 to 1000)
              I (float): Integral reset (0.1 to 1000) [value/s]
              D (float): Derivative rate (0 to 200) [%]
              None if read
           Returns:
              None if set
              p (float): P
              i (float): I
              d (float): D
        """
        self._channel = channel
        print(self._channel)
        kp = kwargs.get("P")
        ki = kwargs.get("I")
        kd = kwargs.get("D")
        if len(kwargs):
            kpc, kic, kdc = self.send_cmd("PID?").split(",")
            if kp is None:
                kp = kpc
            if ki is None:
                ki = kic
            if kd is None:
                kd = kdc
            self.send_cmd("PID", kp, ki, kd)
        else:
            try:
                kp, ki, kd = self.send_cmd("PID?").split(",")
                return float(kp), float(ki), float(kd)
            except (ValueError, AttributeError):
                raise RuntimeError("Invalid answer from the controller")

    def _cmode(self, channel, mode):
        """ Read/Set Control Loop Mode
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
               mode (int): control mode. Valid entries: 1=Manual PID,
                           2=Zone, 3=Open Loop, 4=AutoTune PID,
                           5=AutoTune PI, 6=AutoTune P
          Returns:
               None if set
               mode (int): mode
        """
        self._channel = channel

        if mode is not None:
            if mode not in [1, 2, 3, 4, 5, 6]:
                raise ValueError("Bad value for cmode %r [should be 1->6]" % mode)
            self.send_cmd("CMODE", mode)
        else:
            return self.MODE340[int(self.send_cmd("CMODE?"))]

    def _cset(self, channel, **kwargs):
        """ Read/Set Control Loop Parameters
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
            Kwargs:
               input (str): which input to control from. Valid entries: A or B
               units (int): 1 = Kelvin, 2 = Celsius, 3 = sensor unit
               onoff (bool): switch on (True) or off (False) the control loop
          Returns:
               None if set
               input (str): which input to control from
               units (str): Kelvin, Celsius, sensor unit
               onoff (bool): control loop on/off
        """

        self._channel = channel
        input = kwargs.get("input")
        units = kwargs.get("units")
        onoff = kwargs.get("onoff")

        if input is None and units is None and onoff is None:
            asw = self.send_cmd("CSET?").split(",")
            input = asw[0]
            units = self.REVUNITS340[int(asw[1])]
            onoff = "on" if bool(int(asw[2])) else "off"
            return (input, units, onoff)
        else:
            inputc, unitsc, onoffc, powerup_enable_unused = self.send_cmd(
                "CSET?"
            ).split(",")
            if input is None:
                input = inputc
            if units is None:
                units = unitsc
            elif units != "Kelvin" and units != "Celsius" and units != "Sensor unit":
                return print(
                    "Error: acceptables values for units are "
                    "'Kelvin' or 'Celsius' or 'Sensor unit'."
                )
            else:
                units = self.UNITS340[units]
            if onoff is None:
                onoff = onoffc
            elif onoff != "on" and onoff != "off":
                return print("Error: acceptables values for onoff are 'on' or 'off'.")
            else:
                onoff = 1 if onoff == "on" else 0

            self.send_cmd("CSET", input, units, onoff)

    def send_cmd(self, command, *args):
        """Send a command to the controller
           Args:
              command (str): The command string
              args: Possible variable number of parameters
           Returns:
              None
        """

        ################### print("command = {0}".format(command))

        if command.startswith("*"):
            if "?" in command:
                ans = self._comm.write_readline(command.encode() + self.eos.encode())
                return ans.decode()
            else:
                self._comm.write(command.encode() + self.eos.encode())
        elif "?" in command:
            if "CRVHDR" in command or "RANGE" in command:
                cmd = command
            else:
                if isinstance(self._channel, str):
                    cmd = command + " %s" % self._channel
                else:
                    cmd = command + " %r" % self._channel
            ans = self._comm.write_readline(cmd.encode() + self.eos.encode())
            return ans.decode()
        else:
            if (
                "RANGE" in command
                or "CRVHDR" in command
                or "CRVPT" in command
                or "CRVDEL" in command
                or "CRVSAV" in command
            ):
                value = "".join(str(x) for x in args)
                print("--------- command = {0}".format(command))
                cmd = command + " %s *OPC" % (value) + self.eos
            else:
                inp = ",".join(str(x) for x in args)
                if isinstance(self._channel, str):
                    cmd = command + " %s,%s *OPC" % (self._channel, inp) + self.eos
                else:
                    cmd = command + " %d,%s *OPC" % (self._channel, inp) + self.eos

            self._comm.write(cmd.encode())

    def wraw(self, string):
        """Write a string to the controller
           Args:
              string The complete raw string to write (except eos)
                     Normaly will use it to set a/some parameter/s in 
                     the controller.
           Returns:
              None
        """

        print("string = {0}".format(string))
        cmd = string + " *OPC" + self.eos
        self._comm.write(cmd.encode())

    def rraw(self):
        """Read a string from the controller
           Returns:
              response from the controller
        """

        cmd = self.eos
        ans = self._comm.readline(cmd.encode())
        return ans.decode()

    def wrraw(self, string):
        """Write a string to the controller and then reading answer back
           Args:
              string The complete raw string to write (except eos)
           Returns:
              response from the controller
        """

        print("string = {0}".format(string))
        cmd = string + self.eos
        ans = self._comm.write_readline(cmd.encode())
        return ans.decode()


class lakeshore340(Base):
    def __init__(self, config, *args):
        comm_type = None
        extra_param = None
        if "gpib" in config:
            comm_type = "gpib"
            url = config["gpib"]["url"]
            extra_param = config["gpib"]["pad"]
            eos = config.get("gpib").get("eos", "\r\n")
        elif "serial" in config:
            comm_type = "serial"
            url = config["serial"]["url"]
            extra_param = config.get("serial").get("baudrate")
            eos = config.get("serial").get("eos", "\r\n")
        elif "tcp" in config:
            comm_type = "tcp"
            url = config["tcp"]["url"]
            eos = config.get("tcp").get("eos", "\r\n")
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore340(comm_type, url, extra_param=extra_param, eos=eos)

        model = _lakeshore._model()

        if model != 340:
            raise ValueError(
                "Error, the Lakeshore model is {0}. It should be 340.".format(model)
            )
        # else:
        #     print("\t\t\tthe model is {0}".format(model))

        Base.__init__(self, _lakeshore, config, *args)
