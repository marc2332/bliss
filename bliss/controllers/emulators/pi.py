# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PI (Physik Instrumente) emulator helper classes

To create a pure PI device use the following configuration as
a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
        - class: PI_E712
          module: pi
          model: 6CD         # optional (default is 3CD)
          transports:
              - type: tcp
                url: :25000

To start the server you can do something like::

    $ python -m bliss.controllers.emulator my_emulator

A simple *nc* client can be used to connect to the instrument::

    $ nc 0 25000
    *idn?
    (c)2013 Physik Instrumente(PI) Karlsruhe, E-712.6CD, 0, 0.1.0

"""

import weakref

from .scpi import SCPI


class PI(SCPI):

    def __init__(self, *args, **kwargs):
        super(PI, self).__init__(*args, **kwargs)
        self._manufacturer = '(c)2013 Physik Instrumente(PI) Karlsruhe'


class PIAxis(object):

    def __init__(self, pi, channel=None):
        self._pi = weakref.ref(pi)
        self._channel = channel
        self.__pos = 0.0
        self.__set_mov = 0.0
        self.__set_sva = 0.0
        self.__vol = 0.0
        self.__svo = 0
        self.__ont = 1
        self.__cto = 3, 3, 1, 5, 0, 1, 6, 100, 1, 7, 0

    @property
    def pos(self):
        return '  {0}'.format(self.__pos)

    @property
    def mov(self):
        return '  {0}'.format(self.__set_mov)

    @mov.setter
    def mov(self, new_pos):
        self.__pos = new_pos
        self.__set_mov = new_pos

    @property
    def sva(self):
        return '  {0}'.format(self.__set_sva)

    @sva.setter
    def sva(self, new_pos):
        self.__pos = new_pos
        self.__set_sva = new_pos

    @property
    def vol(self):
        return 'VOL={0}'.format(self.__vol)

    @property
    def svo(self):
        return '  {0}'.format(self.__svo)

    @svo.setter
    def svo(self, yesno):
        self.__svo = yesno

    @property
    def ont(self):
        return '  {0}'.format(self.__ont)

    def cto(self, *args):
        self.__cto = args


class PI_E712(PI):
    """
    Modular digital controller for multi- axis piezo nanopositioning systems
    with capacitive sensors
    """

    def __init__(self, name, axes=None, **opts):
        model = opts.pop('model', 'E-712.3CD')
        super(PI_E712, self).__init__(name, **opts)
        self._model = model
        axes_dict = {}
        if axes is None:
            n = 3 if '3C' in model else 6
            axes = [dict(channel=c) for c in range(1, n+1)]
        for axis in axes:
            axes_dict[axis['channel']] = PIAxis(self, **axis)
        self._axes = axes_dict
        for k, v in opts.items():
            setattr(self, "_" + k, v)

    def pos(self, channel):
        return self._axes[int(channel)].pos

    def mov(self, is_query, channel, new_pos=None):
        axis = self._axes[int(channel)]
        if is_query:
            return axis.mov
        axis.mov = new_pos

    def sva(self, is_query, channel, new_pos=None):
        axis = self._axes[int(channel)]
        if is_query:
            return axis.sva
        axis.sva = new_pos

    def svo(self, is_query, channel, yesno=None):
        axis = self._axes[int(channel)]
        if is_query:
            return axis.svo
        axis.svo = yesno

    def ont(self, channel):
        return self._axes[int(channel)].ont

    def cto(self, channel, trig_mode, min_threshold, max_threshold, polarity):
        self._axes[int(channel)].cto(trig_mode, min_threshold,
                                     max_threshold, polarity)
