# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Vaisala controller (humidity and temperature)"""

import logging

import gevent
import serial

from bliss.comm.util import get_comm
from bliss.common.utils import OrderedDict


class VaisalaError(Exception):
    pass


class Quantity(dict):

    def __init__(self, name, channel, unit, length='3.4', label=None):
        label = channel if label is None else label
        super(Quantity, self).__init__(name=name, channel=channel,
                                       unit=unit, length=length, label=label)

    def formatter(self):
        return '"{0[label]}=" {0[length]} {0[channel]}'.format(self)


QUANTITIES = dict(
    RH=Quantity('Relative humidity', 'RH', '%'),
    T=Quantity('Temperature', 'T', 'degC'),
    TDF=Quantity('Dewpoint/Frostpoint temperature', 'TDF', 'degC'),
    TD=Quantity('Dewpoint temperature', 'TD', 'degC'),
    A=Quantity('Absolute humidity', 'A', 'g/m**3'),
    X=Quantity('Mixing ratio', 'X', 'g/kg'),
    TW=Quantity('Wetbulb temperature', 'TW', 'degC'),
    H2O=Quantity('Humidity air volume / dry air volume', 'H2O', 'ppmv'),
    PW=Quantity('Water vapor pressure', 'PW', 'hPa'),
    PWS=Quantity('Water vapor saturation pressure', 'PWS', 'hPa'),
    H=Quantity('Enthalpy', 'H', 'kJ/kg'),
    DT=Quantity('Difference T and TDF', 'DT', 'degC')
)


class HMT330(object):
    """
    Vaisala HUMICAP(r) Humidity and temperature transmitter series HMT330

    Recommended setup: On the device display configure the following:

    - serial line: baudrate: 9600 data bits:8 parity:N stop bits: 1 
      flow control: None
    - serial mode: STOP
    - echo: OFF
    
    Example of YAML configuration:

    .. code-block:: yaml

        plugin: bliss
        name: hmt1
        serial:
          url: ser2net://lid312:29000/dev/ttyRP20
        counters:
        - counter name: rh1
          channel: RH              # (1)
        - counter name: t1
          channel: T

    * (1) `channel` is any accepted HMT330 abbreviation quantities.
      Main quantities: 'RH', 'T'.
      Optional: 'TDF', 'TD', 'A', 'X', 'TW', 'H2O', 'PW', 'PWS', 'H', 'DT'
    """

    def __init__(self, name, config):
        self.log = logging.getLogger('{0}({1})'.format(type(self).__name__, 
                                                       name))
        self.config = config
        self.name = name
        self.comm = get_comm(config, eol='\r')

        self.__echo = None
        self.__ftime = None
        self.__fdate = None
        self.__unit = None
        self.__serial_mode = None
        self.__formatter = None

        # initialize response format: date/time, units, labels
        self.comm.flush()
        self.echo = False
        self.serial_mode = 'STOP'
        self.stop()
        self.ftime = False
        self.fdate = False
        self.unit = 'metric'

        form = []
        self.__formatter = OrderedDict()
        for counter_config in config.get('counters', ()):
            channel = counter_config['channel']
            quantity = QUANTITIES[channel]
            counter_config['unit'] = quantity['unit']
            self.__formatter[channel] = quantity
            form.append(quantity.formatter())
        self.formatter = ' #t '.join(form) + ' #r'
    
    def _query(self, *args):
        return self._command(*args, wait_reply=True)

    def _command(self, *args, **kwargs):
        wait_reply = kwargs.pop('wait_reply', True)
        if kwargs:
            raise TypeError('Unsupported args {0}'.format(', '.join(kwargs)))
        msg = ' '.join(args) + '\r\n'
        if wait_reply:
            self.log.debug('Tx: %r', msg)
            result = self.comm.write_readline(msg).strip()
            self.log.debug('Rx: %r', result)
            return result
        else:
            self.log.debug('Tx: %r', msg)
            self.comm.write(msg)

    @property
    def echo(self):
        return self.__echo

    @echo.setter
    def echo(self, onoff):
        if onoff in (True, 'on', 'ON', 1):
            self.__echo = True
        else:
            self.__echo = False
        onoff = 'ON' if self.__echo else 'OFF'
        result = self._command('ECHO', onoff)
        if onoff not in result:
            pass
    
    @property
    def configuration(self):
        """Read the current transmitter configuration"""
        return self._query('?')

    @property
    def modules(self):
        """Information about the optional modules that are connected to the
        transmitter."""
        return self._query('MODS')

    @property
    def version(self):
        """Software version information"""
        return self._query('VERS')

    @property
    def errors(self):
        """Transmitter error messages"""
        return self._query('ERRS')

    @property
    def unit(self):
        return self.__unit

    @unit.setter
    def unit(self, unit):
        u0 = unit[0].upper()
        self.__unit = 'metric' if u0.startswith('M') else 'non-metric'
        self._command('UNIT', u0)

    def set_default_formatter(self):
        return self._command('FORM', '/')

    @property
    def formatter(self):
        return self._query('FORM')

    @formatter.setter
    def formatter(self, form):
        result = self._command('FORM', form)
        if result != b'OK':
            raise ValueError(result)

    @property
    def ftime(self):
        return self.__ftime

    @ftime.setter
    def ftime(self, onoff):
        if onoff in (True, 'on', 'ON', 1):
            self.__ftime = True
        else:
            self.__ftime = False
        onoff = 'ON' if self.__fdate else 'OFF'
        self._command('FTIME', onoff)

    @property
    def fdate(self):
        return self.__fdate

    @fdate.setter
    def fdate(self, onoff):
        if onoff in (True, 'on', 'ON', 1):
            self.__fdate = True
        else:
            self.__fdate = False
        onoff = 'ON' if self.__fdate else 'OFF'
        self._command('FDATE', onoff)

    @property
    def serial_mode(self):
        return self._query('SMODE')

    @serial_mode.setter
    def serial_mode(self, mode):
        mode = mode.upper()
        assert mode in ('STOP', 'SEND', 'RUN', 'POLL', 'MODBUS')
        self.__serial_mode = mode
        self._command('SMODE', mode, wait_reply=False)
        assert mode in self.comm.readline()

    def reset(self):
        self._command('RESET', wait_reply=False)

    def start(self):
        self._command('R', wait_reply=False)

    def stop(self):
        self._command('S', wait_reply=False)

    def measure(self):
        """output the reading once in STOP mode."""
        line = self._query('SEND')
        return self._parse_line(line)

    def _parse_line(self, line):
        line = line.strip()
        result = {}
        for field in line.split('\t'):
            name, value = field.split(' ', 1)
            name = name.replace('=', '').strip().upper()
            try:
                value = float(value)
            except ValueError:
                value = float('nan')
            result[name] = value
        return result

    def _run(self):
        while True:
            line = self.comm.readline()
            try:
                self._latest_point = self._parse_line(line)
            except:
                self.log.debug('got garbage')
        
    def read(self):
        if self.__serial_mode == 'RUN':
            raise NotImplementedError
            #return dict(self._latest_point)
        else:
            return self.measure()

    def __getitem__(self, name):
        if self.__serial_mode == 'RUN':
            raise NotImplementedError
            #data = self._latest_point
        else:
            data = self.measure()
        if isinstance(name, (str, unicode)):
            return data[name.upper()]
        return [data[n.upper()] for n in name]
