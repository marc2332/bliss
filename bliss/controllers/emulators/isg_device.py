# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
:term:`ISG_DEVICE` emulator helper class

To create a pure :term:`ISG_DEVICE` device use the following configuration as
a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
      - class: ISG_DEVICE
        transports:
          - type: serial
            url: :????

To start the server you can do something like::

    $ python -m bliss.controllers.emulator my_emulator

A simple *com*-like (ex:*cutecom*) client can be used to connect to the instrument::

    $ com /dev/???
    ?ver

    $ com /dev/???
    ?info

The main purspose of this module is provide a base :class:`ISG_DEVICE`
class that can be used as a helper for your specific :term:`ISG_DEVICE`
device. Example of usage for a VSCANNER device::

    class VSCANNER(ISG_DEVICE):

        def __init__(self, *args, **kwargs):
            super(VSCANNER, self).__init__(*args, **kwargs)
            self._manufacturer = 'ISG ESRF'
"""

import enum
import inspect
import collections

from bliss.controllers.emulator import BaseDevice


class ISG_DEVICE_Error(enum.Enum):
    ExecutionError = -200, 'Execution error'
    InvalidWhileInLocal = -201, 'Invalid while in local'

    def __str__(self):
        return '{0[0]}, {0[1]}'.format(self.value)


class ISG_DEVICE(BaseDevice):
    """
    Base class for :term:`ISG_DEVICE` based bliss emulator devices
    """

    def __init__(self, name, **opts):
        super_kwargs = dict(newline=opts.pop('newline', self.DEFAULT_NEWLINE))
        super(ISG_DEVICE, self).__init__(name, **super_kwargs)
        self._manufacturer = 'ISG Team'
        self._model = 'Generic ISG Device'
        self._version = '0.0'
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
            print "response=", response
            if isinstance(response, ISG_DEVICE_Error):
                self._error_stack.append(response)
            elif response is not None:
                responses.append(str(response))
        if responses:
            return ';'.join(responses) + '\n'

    def handle_command(self, cmd):
        """
        Returns method corresponding to <cmd> command.
        """
        self._log.info("processing cmd '%s'", cmd)
        cmd = cmd.strip()
        args = cmd.split(' ')
        instr = args[0].lower()
        args = args[1:]
        print "instr = ", instr
        print "args = ", args

        is_query = instr.startswith('?')

        # Removes "?".
        simple_instr = instr.replace('?', '')

        # has isg_device this simple instruction as method ?
        attr = getattr(self, simple_instr, None)

        if attr is None:
            print " no method of this name..."
            if simple_instr in self._data:
                return self._data[simple_instr]
            if is_query:
                # ??? retuns an error ???
                return self.query(simple_instr, *args)
            else:
                return self.write(simple_instr, *args)
        elif callable(attr):
            print " ok a method exists and can be called"
            fargs = inspect.getargspec(attr).args
            if len(fargs) > 1 and fargs[1] == 'is_query':
                args = [is_query] + args
            return attr(*args)
        else:
            print " ok a method exists but not callable ???"
            if is_query:
                return attr

    def info():
        args = map(str, (self._manufacturer, self._model,
                         self._version, self._firmware))
        return ', '.join(args)

    def query(self, instr, *args):
        return SCPIError.ExecutionError

    def write(self, instr, *args):
        if args:
            self._data[instr] = args[0]

    def idn(self):
        args = map(str, (self._manufacturer, self._model,
                         self._version, self._firmware))
        return ', '.join(args)

    def ver(self):
        return self._version

    def cls(self):
        self._log.info('clear')
        # clear SESR
        # clear OPERation Status Register
        # clear QUEStionable Status Register
        self._error_stack.clear()

    def syst_err(self):
        pass

