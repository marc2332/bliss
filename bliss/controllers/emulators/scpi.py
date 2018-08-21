# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
:term:`SCPI` emulator helper class

To create a pure :term:`SCPI` device use the following configuration as
a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
      - class: SCPI
        transports:
          - type: tcp
            url: :25000

To start the server you can do something like::

    $ python -m bliss.controllers.emulator my_emulator

A simple *nc* client can be used to connect to the instrument::

    $ nc 0 25000
    *idn?
    Bliss Team, Generic SCPI Device, 0, 0.1.0

The main purspose of this module is provide a base :class:`SCPI`
class that can be used as a helper for your specific :term:`SCPI`
device. Example of usage for a Tektronix Keithley device::

    class Keithley(SCPI):

        def __init__(self, *args, **kwargs):
            super(PI, self).__init__(*args, **kwargs)
            self._manufacturer = '(c)2013 Tektronix bla bla...'
"""

import copy
import enum
import inspect
import collections

from bliss.comm.scpi import Commands
from bliss.controllers.emulator import BaseDevice


class SCPIError(enum.Enum):
    ExecutionError = -200, "Execution error"
    InvalidWhileInLocal = -201, "Invalid while in local"

    def __str__(self):
        return "{0[0]}, {0[1]}".format(self.value)


class SCPI(BaseDevice):
    """
    Base class for :term:`SCPI` based bliss emulator devices
    """

    Manufacturer = "Bliss Team"
    Model = "Generic SCPI Device"
    Version = "0"
    Firmware = "0.1.0"
    IDNFieldSep = ", "

    def __init__(self, name, **opts):
        super_kwargs = dict(newline=opts.pop("newline", self.DEFAULT_NEWLINE))
        super(SCPI, self).__init__(name, **super_kwargs)
        self._data = {}
        self._error_stack = collections.deque()
        self._commands = Commands(opts.get("commands", {}))
        for cmd_expr, cmd_info in self._commands.command_expressions.items():
            min_name = (
                cmd_info["min_command"].lower().replace("*", "").replace(":", "_")
            )
            func = getattr(self, min_name, None)
            if func:
                cmd_info["func"] = func
            if "default" in cmd_info:
                cmd_info["value"] = cmd_info["default"]

    def handle_line(self, line):
        self._log.info("processing line %r", line)
        line = line.strip()
        responses = []
        for cmd in line.split(";"):
            cmd = cmd.strip()
            response = self.handle_command(cmd)
            if isinstance(response, SCPIError):
                self._error_stack.append(response)
            elif response is not None:
                responses.append(str(response))
        if responses:
            return ";".join(responses) + "\n"

    def handle_command(self, cmd):
        self._log.debug("processing cmd %r", cmd)
        cmd = cmd.strip()
        args = cmd.split(" ")
        instr = args[0].lower()
        args = args[1:]
        is_query = instr.endswith("?")
        instr = instr.rstrip("?")
        cmd_info = self._commands.get(instr)
        attr = cmd_info.get("func")
        result = None
        if attr is None:
            if "value" in cmd_info:
                result = cmd_info["value"]
            if is_query:
                result = self.query(cmd_info["min_command"], *args)
            else:
                result = self.write(cmd_info["min_command"], *args)
        elif callable(attr):
            fargs = inspect.getargspec(attr).args
            if len(fargs) > 1 and fargs[1] == "is_query":
                args = [is_query] + args
            result = attr(*args)
        else:
            if is_query:
                result = attr
        if result:
            self._log.debug("answering cmd %r with %r", cmd, result)
        else:
            self._log.debug("finished cmd %r", cmd)
        return result

    def query(self, instr, *args):
        try:
            cmd = self._commands.get(instr)
            return cmd.get("set", str)(cmd["value"])
        except KeyError:
            return SCPIError.ExecutionError

    def write(self, instr, *args):
        if args:
            self._log.debug("set %r to %r", instr, args[0])
            self._commands.get(instr)["value"] = args[0]

    def idn(self):
        args = map(str, (self.Manufacturer, self.Model, self.Version, self.Firmware))
        return self.IDNFieldSep.join(args)

    def cls(self):
        self._log.debug("clear")
        # clear SESR
        # clear OPERation Status Register
        # clear QUEStionable Status Register
        self._error_stack.clear()

    def opc(self, is_query):
        if is_query:
            return "1"

    def syst_err(self):
        pass
