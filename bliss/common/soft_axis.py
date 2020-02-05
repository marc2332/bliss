# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motors.soft import SoftController
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
    export_to_session=True,
):

    if callable(position):
        position = position.__name__
    if callable(move):
        move = move.__name__
    if callable(stop):
        stop = stop.__name__

    config = {"limits": (low_limit, high_limit), "name": name}

    if tolerance is not None:
        config["tolerance"] = tolerance

    controller = SoftController(name, obj, config, position, move, stop, state)

    controller._init()
    axis = controller.get_axis(name)

    if export_to_session:
        current_session = get_current_session()
        if current_session is not None:
            current_session.env_dict[name] = axis

    return axis
