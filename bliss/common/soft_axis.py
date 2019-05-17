# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motors.soft import SoftController
from bliss.common import session
from bliss.common import mapping
from bliss import setup_globals


def SoftAxis(
    name,
    obj,
    position="position",
    move="position",
    stop=None,
    low_limit=float("-inf"),
    high_limit=float("+inf"),
):

    config = session.get_current().config
    if callable(position):
        position = position.__name__
    if callable(move):
        move = move.__name__
    if callable(stop):
        stop = stop.__name__

    controller = SoftController(
        name,
        obj,
        {
            "position": position,
            "move": move,
            "stop": stop,
            "limits": (low_limit, high_limit),
            "name": name,
        },
    )

    controller._init()
    axis = controller.get_axis(name)
    mapping.register(axis, parents_list=[controller], tag=f"axis.{name}")
    setattr(setup_globals, name, axis)
    return axis
