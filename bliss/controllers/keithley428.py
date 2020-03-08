# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Keithley 428 is a Programmable CurrentAmplifier which converts
fast, small currents to a voltage, which can be easily digitized or
displayed by an oscilloscope, waveform analyzer, or data acquisition
system. It uses a sophisticated “feed-back current” circuit to achieve
both fast risetimes and sub-picoamp noise.
"""

import math

from bliss.comm.util import get_comm

# from bliss.comm.gpib import Gpib


def _simple_cmd(command_name, doco):
    def exec_cmd(self):
        return self.put(command_name)

    return property(exec_cmd, doc=doco)


class keithley428(object):
    def __init__(self, name, config_tree):
        """Keithley428 controller (non-scpi).
        name -- the controller's name
        config_tree -- controller configuration,
        """

        self.name = name
        self._cnx = get_comm(config_tree, eol="", timeout=0.5)
        self._txterm = ""
        self._rxterm = "\r\n"
        try:
            self._cnx._readline(self._rxterm)
        except Exception:
            pass

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
        """ Raw WRITE-READ connection to the Keithley.
        * Add terminator
        * convert in bytes
        * <msg> (str): the message you want to send
        * decode the answer
        """
        command = msg + self._txterm
        command = command.encode()
        _ans = self._cnx.write_readline(command, eol=self._rxterm).decode()
        return _ans

    def put(self, msg):
        """ Raw WRITE connection to the Keithley.
        * Add terminator
        * convert in bytes
        * <msg> (str): the message you want to send

        """
        with self._cnx._lock:
            command = msg + self._txterm
            command = command.encode()
            self._cnx.open()
            self._cnx._write(command)

    def __info__(self):
        info_str = "KEITHLEY K428\n"

        info_str += "COMM:\n"
        info_str += "    " + self._cnx.__info__() + "\n"
        try:
            info_str += f"gain: {self.gain}\n"
            info_str += f"filter_rise_time: {self.filter_rise_time}\n"
            info_str += f"voltage_bias: {self.voltage_bias}\n"
            # info_str += f"current_suppress: {self.current_suppress}\n"
            info_str += f"state: {self.state_str}\n"
            info_str += f"overloaded: {self.overloaded}\n"
            info_str += f"filter state: {self.filter_state}\n"
            info_str += f"auto_filter_state: {self.auto_filter_state}\n"
            info_str += f"zero_check: {self.zero_check}\n"
        except Exception:
            info_str += "\nCannot read info from device\n"

        return info_str

    @property
    def filter_rise_time(self):
        """ Set/query Filter Rise Time """
        result = self.putget("U0X")
        pos = result.index("T") + 1
        result = int(result[pos : pos + 1])
        return (result, self._FilterRiseTimes[result])

    @filter_rise_time.setter
    def filter_rise_time(self, value):
        if value not in self._FilterRiseTimes:
            raise ValueError(f"Filter rise time value {value} out of range (0-9)")
        self.put(f"T{value}X")

    @property
    def gain(self):
        """ Set/query Gain """
        result = self.putget("U0X")
        pos = result.index("R") + 1
        result = int(result[pos : pos + 2])
        return result, self._gainStringArray[result]

    @gain.setter
    def gain(self, value):
        if value not in self._gainStringArray:
            raise ValueError(f"Gain value {value} out of range (0-10)")
        self.put(f"R{value}X")

    @property
    def voltage_bias(self):
        """ Set/query Voltage Bias """
        result = self.putget("U2X")
        pos = result.index("V") + 1
        result = result[pos:]
        return float(result)

    @voltage_bias.setter
    def voltage_bias(self, value):
        if value >= 5.0 or value <= -5.0:
            raise ValueError("Value out of range (-5V to 5v)")
        value = value * 10000 + 0.1
        value = int(value / 25.)
        value = value * 25.0 / 10000.0
        self.put(f"V{value}X")

    @property
    def current_suppress(self):
        """ Set/query Current suppress """
        result = self.putget("")  #  ???????????????????????
        pos = result.index("I") + 1
        result = result[pos:]
        return result

    @current_suppress.setter
    def current_suppress(self, amps):
        absVal = math.fabs(amps)
        currentRangeMax = 0.005
        if absVal > currentRangeMax:
            raise ValueError(f"Current suppress value {amps} out of range (=/-0.005A)")
        currentRange = 0
        for x in range(7, 0, -1):
            currentRangeMax /= 10.0
            if absVal > currentRangeMax:
                currentRange = x
                break
        if currentRange == 0:
            raise ValueError(f"Current suppress value {amps} out of range (too small)")
        self.put(f"S{amps},{currentRange}X")
        errorState = self.putget("U1X")
        if errorState != "42800000000000":
            raise ValueError(f"Failed to set current suppress value {amps}")

    @property
    def state(self):
        """ Query keithley status word """
        result = self.putget("U0X")
        return result

    @property
    def state_str(self):
        ans = self.state
        state_str = ""

        if ans[0:3] != "428":
            state_str += "Not a Keithley 428"
            return state_str
        else:
            state_str += "K428"

        if ans[3] == "A":
            if ans[4] == "0":
                state_str += " - Display:Normal"
            if ans[4] == "1":
                state_str += " - Display:Dim"
            if ans[4] == "2":
                state_str += " - Display:Off"

        if ans[5] == "B":
            if ans[6] == "0":
                state_str += " - VBias:off"
            if ans[6] == "1":
                state_str += " - VBias:on"

        if ans[7] == "C":
            if ans[8] == "0":
                state_str += " - Zcheck:off"
            if ans[8] == "1":
                state_str += " - Zcheck:on"
            if ans[8] == "2":
                state_str += " - Zcheck:zero-correct"

        if ans[24] == "R":
            state_str += " - gain:"
            state_str += f"1e{ans[25:27]}"

        if ans[30] == "T":
            frt = self._FilterRiseTimes[int(ans[31:32])]
            state_str += f" - rise time:{frt}"

        return state_str

    @property
    def overloaded(self):
        """ Query Overload """
        result = self.putget("U1X")
        return bool(int(result[12:13]))

    @property
    def filter_state(self):
        """ Query Filter state """
        result = self.putget("U0X")
        pos = result.index("P") + 1
        result = int(result[pos : pos + 1])
        return "Off" if result == 0 else "On"

    @property
    def auto_filter_state(self):
        """ Query Auto filter state """
        result = self.putget("U0X")
        pos = result.index("Z") + 1
        result = int(result[pos : pos + 1])
        return "Off" if result == 0 else "On"

    @property
    def zero_check(self):
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
