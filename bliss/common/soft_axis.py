# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motors.soft import SoftController
from bliss import global_map, setup_globals
from bliss.common.session import get_current_session


def SoftAxis(
    name,
    obj,
    position="position",
    move="position",
    stop=None,
    state=None,
    low_limit=float("-inf"),
    high_limit=float("+inf"),
    tolerance=None,
):

    if callable(position):
        position = position.__name__
    if callable(move):
        move = move.__name__
    if callable(stop):
        stop = stop.__name__

    config = {
        "position": position,
        "move": move,
        "stop": stop,
        "state": state,
        "limits": (low_limit, high_limit),
        "name": name,
    }

    if tolerance is not None:
        config["tolerance"] = tolerance

    controller = SoftController(name, obj, config)

    controller._init()
    axis = controller.get_axis(name)
    global_map.register(axis, parents_list=[controller], tag=f"axis.{name}")
    current_session = get_current_session()
    setattr(setup_globals, name, axis)
    if current_session is not None:
        current_session.env_dict[name] = axis
    return axis
