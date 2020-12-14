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
    unit=None,
    positioner=False,
):

    # if callable(position):
    #     position = position.__name__
    # if callable(move):
    #     move = move.__name__
    # if callable(stop):
    #     stop = stop.__name__

    config = {
        "low_limit": low_limit,
        "high_limit": high_limit,
        "limits": (low_limit, high_limit),
        "name": name,
    }

    if tolerance is not None:
        config["tolerance"] = tolerance

    if unit is not None:
        config["unit"] = unit

    controller = SoftController(name, obj, config, position, move, stop, state)

    controller._init()
    axis = controller.get_axis(name)
    axis.positioner = positioner

    if export_to_session:
        current_session = get_current_session()
        if current_session is not None:
            if (
                name in current_session.config.names_list
                or name in current_session.env_dict.keys()
            ):
                raise ValueError(
                    f"Cannot export object to session with the name '{name}', name is already taken! "
                )

            current_session.env_dict[name] = axis

    return axis
