# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import AxisState

from . import pi_gcs
from bliss.comm import tcp
from bliss.common import event

from PI_E51X import PI_E51X

"""
Bliss controller for ethernet PI E518 piezo controller.
This controller inherits all methods from PI_E51X.
Only the methods not common to E517 and E518 are redefined here:
   * gating.
Cyril Guilloud ESRF BLISS
Thu 13 Feb 2014 15:51:41
"""


class PI_E518(PI_E51X):
    def __init__(self, *args, **kwargs):
        PI_E51X.__init__(self, *args, **kwargs)

    def _get_cto(self, axis):
        # 24 also for 518 ????
        _ans = [bs.decode() for bs in self.comm.write_readlines(b"CTO?\n", 24)]
        return _ans

    """
    CTO?

    1 1=+0000.1000    ???
    1 2=1             ???
    1 3=3             trigger mode
    1 4=0             ???
    1 5=+0000.0000    min threshold
    1 6=+0001.0000    max threshold
    1 7=1             polarity
    1 12=1            ???
    ...
    """

    def set_gate(self, axis, state):
        """
        CTO  [<TrigOutID> <CTOPam> <Value>]+
         - <TrigOutID> : {1, 2, 3}
         - <CTOPam> :
             - 3: trigger mode
                      - <Value> : {0, 2, 3, 4}
                      - 0 : position distance
                      - 2 : OnTarget
                      - 3 : MinMaxThreshold   <----
                      - 4 : Wave Generator
             - 5: min threshold   <--- must be greater than low limit
             - 6: max threshold   <--- must be lower than high limit
             - 7: polarity : 0 / 1


        ex :      ID trigmod min/max       ID min       ID max       ID pol +
              CTO 1  3       3             1  5   0     1  6   100   1  7   1

        Args:
            - <state> : True / False
        Returns:
            -
        Raises:
            ?
        """
        print("   TO BE CHANGED fro E518")
