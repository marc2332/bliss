# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.comm.gpib import Gpib
import math


def _simple_cmd(command_name, doco):
    def exec_cmd(self):
        return self.put(command_name)

    return property(exec_cmd, doc=doco)


class keithley428(object):
    def __init__(self, name, config_tree):
        """Keithley428 controller (non-scpi).
        name -- the controller's name
        config_tree -- controller configuration,
        in this dictionary we need to have:
        gpib_url -- url of the gpib controller i.s:enet://gpib0.esrf.fr
        gpib_pad -- primary address of the musst controller
        gpib_timeout -- communication timeout, default is 1s
        gpib_eos -- end of line termination
        """

        self.name = name
        if "gpib_url" in config_tree:
            self._cnx = Gpib(
                config_tree["gpib_url"],
                pad=config_tree["gpib_pad"],
                eos=config_tree.get("gpib_eos", ""),
                timeout=config_tree.get("gpib_timeout", 0.5),
            )
            self._txterm = ""
            self._rxterm = "\r\n"
            self._cnx._readline(self._rxterm)
        else:
            raise ValueError("Must specify gpib_url")

        self._FilterRiseTimes = {
            0: "10usec",
            1: "30usec",
            2: "100usec",
            3: "300usec",
            4: "1msec",
            5: "3msec",
            6: "10msec",
            7: "30msec",
            8: "100msec",
            9: "300msec",
        }
        self._gainStringArray = {
            0: "1E03V/A",
            1: "1E03V/A",
            2: "1E03V/A",
            3: "1E03V/A",
            4: "1E04V/A",
            5: "1E05V/A",
            6: "1E06V/A",
            7: "1E07V/A",
            8: "1E08V/A",
            9: "1E09V/A",
            10: "1E10V/A",
        }

    VoltageBiasOff = _simple_cmd("B0X", "Turn voltage bias off")
    VoltageBiasOn = _simple_cmd("B1X", "Turn voltage bias on")
    ZeroCheckOff = _simple_cmd("C0X", "Turn zero check off")
    ZeroCheckOn = _simple_cmd("C1X", "Turn zero check on")
    PerformZeroCorrect = _simple_cmd("C2X", "Perform auto zero correct")
    CurrentSuppressOff = _simple_cmd("N0X", "Turn current suppress off")
    CurrentSuppressOn = _simple_cmd("N1X", "Turn current suppress on")
    PerformAutoSuppress = _simple_cmd(
        "C0N2X", "Turn zero check off & perform auto suppress"
    )
    FilterOff = _simple_cmd("P0X", "Turn filter off")
    FilterOn = _simple_cmd("P1X", "Turn filter on")
    AutoFilterOff = _simple_cmd("Z0X", "Turn auto filter off")
    AutoFilterOn = _simple_cmd("Z1X", "Turn auto filter on")
    DisableAutoRange = _simple_cmd("S,10X", "Disable auto ranging")
    EnableAutoRange = _simple_cmd("S,0X", "Enable auto ranging")
    X10GainOff = _simple_cmd("W0X", "Disable X10 gain setting")
    X10GainOn = _simple_cmd("W1X", "Enable X10 gain setting")

    def putget(self, msg):
        """ Raw connection to the Keithley.
        msg -- the message you want to send
        """
        return self._cnx.write_readline(msg + self._txterm, eol=self._rxterm)

    def put(self, msg):
        """ Raw connection to the Keithley.
        msg -- the message you want to send
        """
        with self._cnx._lock:
            self._cnx.open()
            self._cnx._write(msg + self._txterm)

    @property
    def FilterRiseTime(self):
        """ Set/query Filter Rise Time """
        result = self.putget("U0X")
        pos = result.index("T") + 1
        result = int(result[pos : pos + 1])
        return (result, self._FilterRiseTimes[result])

    @FilterRiseTime.setter
    def FilterRiseTime(self, value):
        if value not in self._FilterRiseTimes:
            raise ValueError(
                "Filter rise time value {0} out of range (0-9)".format(value)
            )
        self.put("T{0}X".format(value))

    @property
    def Gain(self):
        """ Set/query Gain """
        result = self.putget("U0X")
        pos = result.index("R") + 1
        result = int(result[pos : pos + 2])
        return result, self._gainStringArray[result]

    @Gain.setter
    def Gain(self, value):
        if value not in self._gainStringArray:
            raise ValueError("Gain value {0} out of range (0-10)".format(value))
        self.put("R{0}X".format(value))

    @property
    def VoltageBias(self):
        """ Set/query Voltage Bias """
        result = self.putget("U2X")
        pos = result.index("V") + 1
        result = result[pos:]
        return float(result)

    @VoltageBias.setter
    def VoltageBias(self, value):
        if value >= 5.0 or value <= -5.0:
            raise ValueError("Value out of range (-5V to -5v)")
        value = value * 10000 + 0.1
        value = int(value / 25.)
        value = value * 25.0 / 10000.0
        self.put("V{0}X".format(value))

    @property
    def CurrentSuppress(self):
        """ Set/query Current suppress """
        result = self.putget("")
        pos = result.index("I") + 1
        result = result[pos:]
        return result

    @CurrentSuppress.setter
    def CurrentSuppress(self, amps):
        absVal = math.fabs(amps)
        currentRangeMax = 0.005
        if absVal > currentRangeMax:
            raise ValueError(
                "Current suppress value {0} out of range (=/-0.005A)".format(amps)
            )
        currentRange = 0
        for x in range(7, 0, -1):
            currentRangeMax /= 10.0
            if absVal > currentRangeMax:
                currentRange = x
                break
        if currentRange == 0:
            raise ValueError(
                "Current suppress value {0} out of range (too small)".format(amps)
            )
        self.put("S{0},{1}X".format(amps, currentRange))
        errorState = self.putget("U1X")
        if errorState != "42800000000000":
            raise ValueError("Failed to set current suppress value {0}".format(amps))

    @property
    def State(self):
        """ Query keithley status word """
        result = self.putget("U0X")
        return result

    @property
    def Overloaded(self):
        """ Query Overload """
        result = self.putget("U1X")
        return bool(int(result[12:13]))

    @property
    def FilterState(self):
        """ Query Filter state """
        result = self.putget("U0X")
        pos = result.index("P") + 1
        result = int(result[pos : pos + 1])
        return "Off" if result == 0 else "On"

    @property
    def AutoFilterState(self):
        """ Query Auto filter state """
        result = self.putget("U0X")
        pos = result.index("Z") + 1
        result = int(result[pos : pos + 1])
        return "Off" if result == 0 else "On"

    @property
    def ZeroCheck(self):
        """ Query ZeroCheck state """
        result = self.putget("U0X")
        pos = result.index("C") + 1
        result = int(result[pos : pos + 1])
        if result == 0:
            return "Off"
        elif result == 1:
            return "On"
        else:
            return "Zero correct last sent"
