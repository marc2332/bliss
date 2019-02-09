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
import enum
import inspect
import collections

from .emulator import BaseDevice


class VSAxis(object):
    def __init__(self, vscanner, channel=None):
        self._vscanner = weakref.ref(vscanner)
        self._channel = channel
        self.__pos = 0.0

    @property
    def pos(self):
        return "  {0}".format(self.__pos)

    @pos.setter
    def pos(self, new_pos):
        self.__pos = float(new_pos)


class VSCANNER(BaseDevice):
    """
    Dual channel voltage controller 0-10 V
    """

    def __init__(self, name, axes=None, **opts):
        super(VSCANNER, self).__init__(name, **opts)

        self._model = "VSCANNER"
        self._version = 3.14
        self._manufacturer = "ESRF ISG vscanner"

        axes_dict = {}

        if axes is None:
            n = 2
            axes = [{"channel": "X"}, {"channel": "Y"}]

        for axis in axes:
            axes_dict[axis["channel"]] = VSAxis(self, **axis)

        self._axes = axes_dict

        self._axes["X"].pos = 0.321
        self._axes["Y"].pos = 0.123

    def handle_line(self, line):
        cmd = line.rstrip()
        print("RECU : %r" % cmd)

        if cmd == "?VER":
            _ans = "VSCANNER 01.02\r\n"
            print("  returns %s" % _ans)
            return _ans

        if cmd == "?VXY":
            _posX = self._axes["X"].pos
            _posY = self._axes["Y"].pos
            _ans = "%s %s" % (_posX, _posY)
            print("  returns %s" % _ans)
            return _ans

        if cmd == "?VX":
            _posX = self._axes["X"].pos
            _ans = "%s \n" % _posX
            print("  returns %s" % _ans)
            return _ans

        if cmd == "?VY":
            _posY = self._axes["Y"].pos
            _ans = "%s \n" % _posY
            print("  returns %s" % _ans)
            return _ans

        if cmd == "?STATE":
            print("  returns READY")
            return "READY\n"

        if cmd == "?ERR":
            print("  returns OK")
            return "OK\n"

        if cmd == "?VEL":
            print("  vel-> returns '0.2 0.1' (with single quotes)")
            return "'0.2 0.1'\n"

        if cmd == "":
            print(" no command ?")
            pass

        if cmd.startswith("LINE"):
            arg1 = cmd.split()[1]
            arg2 = cmd.split()[2]
            Xrel = float(arg1)
            Yrel = float(arg2)
            print(("  move X by %g Y by %g" % (Xrel, Yrel)))
            new_X_pos = float(self._axes["X"].pos) + Xrel
            new_Y_pos = float(self._axes["Y"].pos) + Yrel
            self._axes["X"].pos = new_X_pos
            self._axes["Y"].pos = new_Y_pos
            print(
                (
                    " new x=%g  y=%g"
                    % (float(self._axes["X"].pos), float(self._axes["Y"].pos))
                )
            )

        if cmd.startswith("VXY"):
            xnew = float(cmd.split()[1])
            ynew = float(cmd.split()[2])
            print("move X to %g Y to %g" % (xnew, ynew))
            self._axes["X"].pos = xnew
            self._axes["Y"].pos = ynew

        if cmd.startswith("VX"):
            arg = cmd.split()[1]
            self._axes["X"].pos = float(arg)
            print("moves X to %g" % float(self._axes["X"].pos))

        if cmd.startswith("VY"):
            arg = cmd.split()[1]
            self._axes["Y"].pos = float(arg)
            print("moves Y to %g" % float(self._axes["Y"].pos))
