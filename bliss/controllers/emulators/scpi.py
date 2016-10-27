# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
SCPI emulator helper class

To create a pure SCPI_ device use the following configuration as
a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
        - class: SCPI
          transports:
              - type: tcp
                url: :25000

To start the server you can do something like:

    $ python -m bliss.controllers.emulator my_emulator

A simple *nc* client can be used to connect to the instrument:

    $ nc 0 25000
    *idn?
    Bliss Team, Generic SCPI Device, 0, 0.1.0

"""

import enum
import inspect
import collections

from bliss.controllers.emulator import BaseDevice


class SCPIError(enum.Enum):
    ExecutionError = -200, 'Execution error'
    InvalidWhileInLocal = -201, 'Invalid while in local'

    def __str__(self):
        return '{0[0]}, {0[1]}'.format(self.value)


class SCPI(BaseDevice):

    def __init__(self, name, **opts):
        super_kwargs = dict(newline=opts.pop('newline', self.DEFAULT_NEWLINE))
        super(SCPI, self).__init__(name, **super_kwargs)
        self._manufacturer = 'Bliss Team'
        self._model = 'Generic SCPI Device'
        self._version = '0'
        self._firmware = '0.1.0'
        self._data = {}
        self._error_stack = collections.deque()

    def handle_line(self, line):
        self._log.info("processing line '%s'", line)
        line = line.strip()
        responses = []
        for cmd in line.split(';'):
            cmd = cmd.strip()
            response = self.handle_command(cmd)
            if isinstance(response, SCPIError):
                self._error_stack.append(response)
            elif response is not None:
                responses.append(str(response))
        if responses:
            return ';'.join(responses) + '\n'

    def handle_command(self, cmd):
        self._log.info("processing cmd '%s'", cmd)
        cmd = cmd.strip()
        args = cmd.split(' ')
        instr = args[0].lower()
        args = args[1:]
        is_query =  instr.endswith('?')
        if instr.startswith(':'):
            instr = instr[1:]
        if is_query:
            instr = instr[:-1]
        simple_instr = instr.replace('*', '').replace(':', '_')
        attr = getattr(self, simple_instr, None)
        if attr is None:
            if simple_instr in self._data:
                return self._data[simple_instr]
            if is_query:
                return self.query(simple_instr, *args)
            else:
                return self.write(simple_instr, *args)
        elif callable(attr):
            fargs = inspect.getargspec(attr).args
            if len(fargs) > 1 and fargs[1] == 'is_query':
                args = [is_query] + args
            return attr(*args)
        else:
            if is_query:
                return attr

    def query(self, instr, *args):
        return SCPIError.ExecutionError

    def write(self, instr, *args):
        if args:
            self._data[instr] = args[0]

    def idn(self):
        args = map(str, (self._manufacturer, self._model,
                         self._version, self._firmware))
        return ', '.join(args)

    def cls(self):
        self._log.info('clear')
        # clear SESR
        # clear OPERation Status Register
        # clear QUEStionable Status Register
        self._error_stack.clear()

    def syst_err(self):
        pass

