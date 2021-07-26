# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
FiberOptic Intralux DC-1100 - Cold Light Source
"""

import time

from bliss import global_map
from bliss.comm.util import get_comm, SERIAL
from bliss.common.utils import autocomplete_property
from bliss.comm.serial import SerialTimeout


TRIGGER_CODES = {"0": "HIGH ACTIVE", "1": "LOW ACTIVE"}

SOURCE_CODES = {"1": "POTENTIOMETER", "2": "ANALOG IN", "4": "COM PORT"}

MODUS_CODES = {
    "01": "Standby",
    "02": "On",
    "04": "MultiPort",
    "08": "undef",
    "16": "Error",
}

ERROR_CODES = {
    "0": "No Error",
    "1": "Overheat",
    "2": "LED Failure 1",
    "4": "LED Failure 2",
}


class IntraledController:
    """
    Intraled controller
    """

    def __init__(self, config, name):
        self.name = name
        try:
            self.comm = get_comm(config, ctype=SERIAL, timeout=1)
        except SerialTimeout as com_exc:
            _msg = f"{self.name} Serial Timeout: Cannot connect to Serial : {config}"
            raise RuntimeError(_msg) from com_exc

        self.last_status = None

    def send(self, command):
        """
        Send a command and check acknowledge from the device.
        * Add starting character '>'.
        * Add term characters.
        * Encode string.
        CYRIL [15]: ser0.write_readline(b'>si00100\r\n', eol='\r\n')
        Out [15]: b'>si00100'

        Param:
            <command>: (str): ex: 'si00100'

        Return:
            str: Decoded string with starting char '>' removed.

        """
        formated_command = ">" + command + "\r\n"
        formated_command = formated_command.encode()
        # print("FC=", formated_command)

        try:
            raw_ans = self.comm.write_readline(formated_command, eol=b"\r\n")
        except SerialTimeout as com_exc:
            _msg = f"{self.name} Serial Timeout: Cannot connect to Serial: {self.comm.__info__()}"
            raise RuntimeError(_msg) from com_exc

        # print("RA=", raw_ans)
        ans = raw_ans.decode()[1:]
        return ans

    def get_intensity(self):
        """
        # Get Intensity
        # 100 * 0.1 % -> 10%
        """
        raw_ans = self.send("gi")
        if raw_ans[0:2] == "gi":
            raw_val = int(raw_ans[3:]) * 0.1
            ans = float(f"{raw_val:g}")
            return ans
        else:
            raise RuntimeError(f"Error reading intensity (raw_ans={raw_ans})")

    def set_intensity(self, value):
        """
        Set I
        """
        if value < 0 or value > 100:
            raise ValueError(f"Invalid intensity {value}")

        si_cmd = f"si{int(value * 10):05}"
        # print("si_cmd=", si_cmd)
        si_ans = self.send(si_cmd)
        # print("si_ans = ", si_ans)
        if si_ans != si_cmd:
            print("set_intensity: hummm louche", si_ans, si_cmd)

    def get_fw_version(self):
        """
        # Get firwmare version
        # 30 * 0.1% -> v3.0
        CYRIL [20]: ser0.write_readline(b">gz\r\n", eol=b"\r\n")
        Out [20]: b'>gz00030'
        """
        return self.send(">gz")

    def get_temperature(self):
        """
        Return:
            float: Temperature read from device in degree Celcius.
        raw_ans ≈ 'gt00356'
        """
        raw_ans = self.send("gt")
        if raw_ans[0:2] == "gt":
            return float(f"{int(raw_ans[2:]) * 0.1:g}")
        else:
            raise RuntimeError(f"Error reading temperature (raw_ans={raw_ans}")

    def update_status(self):
        """
        Read and decode device status.
        raw_ans ≈ 'gs04020'

        Return:
            dict:
            * trigger: str
            * source: str
            * modus: str
            * error: str


        CYRIL [10]: with bench():
        ...:     ss= il5._controller.get_status()
        Execution time: 64ms 525μs
        """
        _t0 = time.time()
        # print("reading status")
        raw_ans = self.send("gs")
        if raw_ans[0:2] != "gs":
            raise RuntimeError(f"Error reading status (raw_ans={raw_ans})")

        status = dict()

        trigger_code = raw_ans[2:3]
        source_code = raw_ans[3:4]
        modus_code = raw_ans[4:6]
        error_code = raw_ans[6:7]

        status["trigger"] = TRIGGER_CODES[trigger_code]
        status["source"] = SOURCE_CODES[source_code]
        status["modus"] = MODUS_CODES[modus_code]
        status["error"] = ERROR_CODES[error_code]

        self.last_status = status
        self.last_status["last_read"] = time.time()
        self.last_status["last_duration"] = self.last_status["last_read"] - _t0

    def get_status(self):
        """
        Read status from device (if needed).
        Needed means: None or aged of more than 100 ms
        """
        if self.last_status is None:
            self.update_status()
        else:
            if time.time() - self.last_status["last_read"] > 0.1:
                self.update_status()

        return self.last_status

    def get_param(self, param):
        """
        Return:
            str: status parameter coresponding to 'param'
        """
        return self.get_status()[param]


class Intraled:
    """
    Intraled interface object.
    """

    def __init__(self, name, config):
        self.name = name
        self._controller = IntraledController(config, name)

        global_map.register(
            self, children_list=[self._controller.comm], tag=f"Intralux:{name}"
        )

    def __info__(self):
        """
        Online info
        """
        info_str = f"INTRALED {self.name}:\n"
        info_str += f"   Intensity: {self.intensity} %\n"
        info_str += f"   Temperature: {self.temperature} °C\n"
        info_str += f"   Source: {self.source}\n"
        info_str += f"   Mode: {self.modus}\n"
        info_str += "\n"
        info_str += self._controller.comm.__info__()

        return info_str

    @autocomplete_property
    def intensity(self):
        """
        Return:
            float: intensity read from device.
        """
        return self._controller.get_intensity()

    @intensity.setter
    def intensity(self, intensity_value):
        """
        Set intensity (0 - 100 %)

        Param:
            <intensity_value>: float in [0 ; 100]
        """
        if self.modus in ["Standby", "MultiPort"]:
            _msg = f"Cannot set intensity: {self.name} is in {self.modus} mode (check rear switch)."
            raise RuntimeError(_msg)
        else:
            self._controller.set_intensity(intensity_value)

    def off(self):
        """
        Switch light OFF by setting intensity to 0.
        """
        self.intensity = 0

    def on(self):
        """
        Switch light ON
        Q: which value ?
           -> the minimum to have light ie 1.1%
        TODO: use a setting ?
        """
        self.intensity = 1.1

    @autocomplete_property
    def temperature(self):
        """
        Return:
            float (RO): Temperature in degree Celsius.
        """
        return self._controller.get_temperature()

    @autocomplete_property
    def source(self):
        """
        Source of intensity control.

        The source switches automaticaly from POTENTIOMETER to COM_PORT when
        intensity is set via serial line.

        Return:
            str: source of the intensity setting:
                 'POTENTIOMETER' or 'ANALOG IN' or 'COM PORT'
        """
        return self._controller.get_param("source")

    @source.setter
    def source(self, value):
        """
        Select source of intensity control.
        Param:
            value: str in ['POTENTIOMETER', 'ANALOG IN', 'COM PORT']
        """
        if value not in SOURCE_CODES.values:
            raise ValueError(f"Invalid value: {value}")

        self._controller.set_source(value)

    @autocomplete_property
    def trigger_logic(self):
        """
        """
        return self._controller.get_param("trigger")

    @autocomplete_property
    def modus(self):
        """
        """
        return self._controller.get_param("modus")

    @autocomplete_property
    def error(self):
        """
        """
        return self._controller.get_param("error")
