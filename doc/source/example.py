# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""IcePAP motor controller

To instantiate a new IcePAP motor controller, configure it with:

.. code-block:: yaml

    plugin: emotion
    class: IcePAP
    host: iceid00a
    axes:
      - name: th
        address: 01
        unit: deg
        steps_per_unit: 1
        velocity: 0        # unit/s
        acceleration: 0    # unit/s/s
        backlash:          # unit

... and so on and so forth

.. autosummary::
    :nosignatures:
    :toctree:

    libicepap
"""

__all__ = ['IcePAP']

import os
import sys
import string

import gevent

from bliss.controllers.motor import Controller


class IcePAP(Controller):
    """
    The IcePAP motor controller.
    """

    def move(self, axis, position, wait=False):
        """
        move the given axis to the given absolute position

        Note:
            using `wait=True` will block the current :class:`~gevent.Greenlet`.

        See Also:
            :meth:`~IcePAP.rmove`

        Args:
            axis (int): valid axis number (1..8, 11..18, ...,)
            position (int): position (steps)
            wait (bool): wait or not for motion to end [default: False]

        Returns:
            int: actual position where motor is (steps)
        """
        pass

