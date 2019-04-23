# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
MCCE (Module de Command et Control des Electrometres)
Serial interface allows remote reading and programming.
The parameters of the serial line are:
8 bits, no parity, 1 stop bit, 9600 bauds
Before sending a set command, the key to be turned off, and back to on after
executing the command.

Example yml file:
class: Mcce
channels:
  -
    name: mcce_ch1
    address: 1
    serial:
      url: "rfc2217://ld231:28100"
  -
    name: mcce_ch2
    address: 2
    serial:
       url: "rfc2217://ld231:28016"
  -
    name: mcce_ch3
    address: 3
    serial:
       url: "rfc2217://ld231:28017"
"""
import enum
from math import log10
import serial
from bliss.comm.serial import Serial


@enum.unique
class McceReadCommands(enum.IntEnum):
    """ The READ commands """

    STATUS = 1
    ERROR = 2
    MODE = 3
    TYPE = 4
    POLARITY = 5
    FREQUENCY = 6
    GAIN = 7
    RANGE = 8
    LOW_LIMIT = 9
    HIGH_LIMIT = 10
    DAC_ZERO = 11
    DAC_OFFSET = 12
    HV = 13
    SOURCE = 14
    PREAMP = 15


@enum.unique
class McceProgCommands(enum.IntEnum):
    """ The PROG commands """

    MODE = 1
    POLARITY = 2
    RANGE1 = 3  # range for type 1 or 6
    RANGE2 = 4  # range for type 2
    RANGE3 = 5  # range for type 3
    RANGE4 = 6  # range for type 4
    RANGE5 = 7  # range for type 5
    GAIN = 8
    FREQUENCY = 9
    SOURCE = 11
    ADDRESS = 12
    DAC_ZERO = 13
    DAC_OFFSET = 14
    LOW_LIMIT = 15
    HIGH_LIMIT = 16
    ANSWER_TYPE = 17
    ERROR_RESET = 18


@enum.unique
class McceRangeUnits(enum.IntEnum):
    """ Possible Range units """

    A = 0
    MOhm = 4
    KOhm = 5


MCCE_RANGE = {
    1: (1e-11, 3e-11, 1e-10, 3e-10),
    2: (1e-10, 3e-10, 1e-9, 3e-9, 1e-8, 3e-8, 1e-7, 3e-7),
    3: (1e-8, 3e-8, 1e-7, 3e-7, 1e-6, 3e-6, 1e-5, 3e-5),
    4: (1000, 300, 100, 30),
    6: (1e-10, 1e-9, 1e-8, 1e-7),
    7: (1000, 300, 100, 30),
}


MCCE_FREQUENCY = (3, 10, 100, 1000)


MCCE_TYPE = {
    1: "Photovoltaic Ultra High Sensitivity",
    2: "Photovoltaic High Sensitivity",
    3: "Photovoltaic Medium Sensitivity",
    4: "Photocondictive High Sensitivity",
    6: "Photovoltaic High Voltage",
}


class McceController:
    """ Commmands """

    def __init__(self, serial_line, address):
        self.serial_line = Serial(
            serial_line,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            eol=b"\r\n",
        )
        self.address = address  # unique address of the channel
        self.remote = True
        self.mcce_range = ()
        self.mcce_gain = None
        self.range_units = McceRangeUnits.A
        self.range_cmd = None
        self.mcce_type = None

    def __repr__(self):
        _ret = "Type: %s (%d)\n" % (MCCE_TYPE[self.mcce_type], self.mcce_type)
        if self.mcce_type in (4, 5):
            _ret += "Gain Scale: 1, 10, 100"
        else:
            _ret += "Frequency Scale: " + str(MCCE_FREQUENCY).replace(",", " ").strip(
                "()"
            )
        _ret += "\nRange Scale: %s\n" % str(self.mcce_range).replace(",", " ").strip(
            "()"
        )
        _ret += self.status
        return _ret

    def init(self):
        """ Set default values, depending on the hardware """
        # short answer
        self._set_on(False)
        self._send_cmd(McceProgCommands.ANSWER_TYPE, 0)
        self._set_on(True)

        # remote control
        self.remote = self.set_remote(True)

        # get the type of the electrometer
        try:
            _type = self._send_cmd(McceReadCommands.TYPE)
            self.mcce_type = _type
            self.mcce_range = MCCE_RANGE[_type]
            if _type in (4, 5):
                self.mcce_gain = (1, 10, 100)
            if _type in McceRangeUnits._value2member_map_:
                self.range_units = McceRangeUnits._value2member_map_[_type]
            if _type == 6:
                self.range_cmd = McceProgCommands.RANGE1
            else:
                self.range_cmd = McceProgCommands._value2member_map_[_type + 2]
        except RuntimeError:
            raise

    def reset(self):
        """ Reset the MCCE """
        self.serial_line.write(b"%d RESET \r\n" % self.address)

    def set_remote(self, remote=True):
        """ Set the control to remote (block the front pannel)
        Args:
           remote (bool): True (Remote), False (Local)
        Returns:
           (bool): True (Remote), False (Local)
        """
        if remote:
            if self._send_cmd("REMOTE"):
                return True
        self._send_cmd("LOCAL")
        return False

    def _set_on(self, value=True):
        """ Set the control on/off (turn front pannel key)
        Args:
           value (bool): True (key to on), False (key to off)
        Returns:
           (bool): True (on), False (off)
        """
        return self._send_cmd("MEASURE", value)

    @property
    def range(self):
        """ Read the electrometer range
        Returns:
            (int): Current range
            (str): Range units
        Raises:
            RuntimeError: Command not executed
        """
        _range = self._send_cmd(McceReadCommands.RANGE)
        return self.mcce_range[_range], self.range_units.name

    @range.setter
    def range(self, value):
        """ Set the range
        Args:
           (int): The desired range
        """
        _range = self.mcce_range.index(value)
        self._set_on(False)
        self._send_cmd(self.range_cmd, _range)
        self._set_on(True)

    @property
    def frequency(self):
        """ Read the frequency filter of the fotovoltaic electrometers.
        Returns:
            (int): The value
        Raises:
           TypeError: No frequency for electrometers type 4 and 5
        """
        if self.mcce_type in (4, 5):
            raise TypeError("No frequency for photocondictive electrometer")

        value = self._send_cmd(McceReadCommands.FREQUENCY)
        return MCCE_FREQUENCY[value]

    @frequency.setter
    def frequency(self, value):
        """ Set the frequency filter of the photovoltaic electrometers.
        Args:
           value(int): Filter value
        Raises:
           TypeError: No frequency for electrometers type 4 and 5
        """
        if self.mcce_type in (4, 5):
            raise TypeError("No frequency for photocondictive electrometer")

        _filter = MCCE_FREQUENCY.index(value)
        self._set_on(False)
        self._send_cmd(McceProgCommands.FREQUENCY, _filter)
        self._set_on(True)

    @property
    def gain(self):
        """ Read the gain of the photoconductive electrometers.
        Returns:
            (int): The gain value
        Raises:
           TypeError: No gain for electrometers type 1,2,3 and 6
        """
        if self.mcce_type in (1, 2, 3, 6):
            raise TypeError("No gain for photovoltaic electrometer")

        value = self._send_cmd(McceReadCommands.GAIN)
        return pow(10, value)

    @gain.setter
    def gain(self, value):
        """ Set the gain of the fotoconductive electrometers
        Args:
           (int): The value
        Raises:
           TypeError: No gain for electrometers type 1,2,3 and 6
        """
        if self.mcce_type in (1, 2, 3, 6):
            raise TypeError("No gain for photovoltaic electrometer")

        _gain = log10(value)
        self._set_on(False)
        self._send_cmd(McceProgCommands.GAIN, _gain)
        self._set_on(True)

    @property
    def polarity(self):
        """ Read the polarity of the current
        Returns:
            (str): positive - input current, negative - output current
         """
        value = self._send_cmd(McceReadCommands.POLARITY)
        if value < 0:
            return "negative"
        return "positive"

    @polarity.setter
    def polarity(self, value):
        """Set the polarity of the current
        Args:
           value(str): + (input) or - (output)
        """
        _polarity = 0
        if value.startswith("-") or value.startswith("n"):
            _polarity = 1

        self._set_on(False)
        self._send_cmd(McceProgCommands.POLARITY, _polarity)
        self._set_on(True)

    @property
    def status(self):
        """ Status of the electrometer """
        _range, _unit = self.range
        _ret = "Range: %g %s\n" % (_range, _unit)
        if self.mcce_type in (4, 5):
            _ret += "Gain: %d\n" % self.gain
        else:
            _ret += "Frequency: %d Hz\n" % self.frequency
        _ret += "Polarity: %s\n" % self.polarity

        return _ret

    def _send_cmd(self, cmd, value=None):
        """ Send a command to the serial line
        Args:
            cmd (string or enum): the bare command
            value (int): Value to set, if any
        Returns:
            (bool) or (int): True, False or the bare answer if command allows
        Raises:
            RuntimeError: Command not executed
        """
        # flush the serial line
        self.serial_line.flush()

        # construct the command
        if isinstance(cmd, str):
            if value is not None:
                _cmd = "%d %s %d \r\n" % (self.address, cmd, value)
            else:
                _cmd = "%d %s \r\n" % (self.address, cmd)

            _asw = self.serial_line.write_readline(_cmd.encode())
            return self._check_answer(_asw.decode())

        if isinstance(cmd, McceProgCommands):
            _cmd = "%d PROG %d %d \r\n" % (self.address, cmd, value)
            _asw = self.serial_line.write_readline(_cmd.encode())
            return self._check_answer(_asw.decode())

        if isinstance(cmd, McceReadCommands):
            _cmd = "%d READ %d \r\n" % (self.address, cmd)
            _asw = self.serial_line.write_readline(_cmd.encode())
            return int(self._check_answer(_asw.decode()))

        return False

    def _check_answer(self, answer):
        """ Check the answer from the serial line
        Args:
            (str): The raw amswer
        Returns:
            (bool) or (string): True if the answer is ACK. The value if any.
        Raises:
            RuntimeError: Command not executed if the answer is NAK
        """
        if "NAK" in answer:
            raise RuntimeError("Command not executed")
        if "ACK" in answer:
            return True
        if "AWR" in answer:
            return answer.split("=")[1].strip()
        return False


class Mcce(McceController):
    """ MCCE class """

    def __init__(self, name, config):
        serial_line = config["serial"]["url"]
        address = config.get("address", 1)
        super().__init__(serial_line, address)
        McceController.init(self)
