# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
VSCANNER (ESRF ISG) emulator helper classes

To create a VSCANNER device, use the following configuration as
a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
        - class: VSCANNER
          transports:
              - type: serial
                url: /dev/pts/???

To start the server you can do something like::

    $ python -m bliss.controllers.emulator my_emulator


"""

import weakref

from .isg_device import ISG_DEVICE

class VSAxis(object):

    def __init__(self, vscanner, channel=None):
        self._vscanner = weakref.ref(vscanner)
        self._channel = channel
        self.__pos = 0.0

    @property
    def pos(self):
        return '  {0}'.format(self.__pos)

class VSCANNER(ISG_DEVICE):
    """
    Dual channel voltage controller 0-10 V
    """
    def __init__(self, name, axes=None, **opts):
        model = opts.pop('model', 'VSCANNER')
        super(VSCANNER, self).__init__(name, **opts)

        self._model = model
        self._version = 3.14
        self._manufacturer = 'ESRF ISG vscanner'

        axes_dict = {}

        if axes is None:
            n = 2
            # change fo X Y ???
            axes = [{'channel': 1}, {'channel': 2}]

        for axis in axes:
            axes_dict[axis['channel']] = VSAxis(self, **axis)

        self._axes = axes_dict

#        for k, v in opts.items():
#            setattr(self, "_" + k, v)

    def pos(self, channel):
        return self._axes[int(channel)].pos


    def ver(self):
        return 'VSCANNER 01.02\r\n'

    def state(self):
        # READY  LWAITING  LRUNNING  PWAITING  PRUNNING
        return "READY"

    def vxy(self):
        return "2.34 3.45"

    def vx(self):
        return "4.56"

    def vy(self, is_query, channel, new_pos=None):
        axis = self._axes[int(channel)]
        if is_query:
            return axis.mov
        axis.mov = new_pos

#     def sva(self, is_query, channel, new_pos=None):
#         axis = self._axes[int(channel)]
#         if is_query:
#             return axis.sva
#         axis.sva = new_pos
# 
#     def svo(self, is_query, channel, yesno=None):
#         axis = self._axes[int(channel)]
#         if is_query:
#             return axis.svo
#         axis.svo = yesno
