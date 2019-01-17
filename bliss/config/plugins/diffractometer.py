# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from .utils import find_class, replace_reference_by_object
from bliss.controllers.diffractometers import get_diffractometer_class
from bliss.controllers.motors.hklmotors import HKLMotors
from bliss.common.axis import Axis, AxisRef
from bliss.config.static import Node


def create_objects_from_config_node(config, cfg_node):
    diff_name = cfg_node["name"]
    diff_geo = cfg_node.get("geometry", None)
    if diff_geo is None:
        raise KeyError("Missing diffractometer geometry name in config")

    diff_class = get_diffractometer_class(diff_geo)
    diff_calc = diff_class(diff_name, cfg_node)
    real_names = list(diff_calc.axis_names)
    pseudo_names = list(diff_calc.pseudo_names)

    axes = list()
    axes_names = list()

    for axis_config in cfg_node.get("axes"):
        axis_name = axis_config.get("name")
        axis_tag = axis_config.get("tags")
        if axis_tag.startswith("real"):
            axis_calc_name = axis_tag.split()[1]
            if axis_calc_name in real_names:
                real_names.remove(axis_calc_name)
            else:
                if axis_calc_name != "energy":
                    raise KeyError(
                        "{0} is not not a valid real axis tag".format(axis_calc_name)
                    )
        else:
            if axis_tag in pseudo_names:
                pseudo_names.remove(axis_tag)
            else:
                raise KeyError("{0} is not a valid pseudo axis tag".format(axis_tag))
        if axis_name.startswith("$"):
            axis_class = AxisRef
            axis_name = axis_name.lstrip("$")
        else:
            axis_class = Axis
            axes_names.append(axis_name)
        axes.append((axis_name, axis_class, axis_config))

    if len(real_names):
        raise KeyError("Missing real axis tags {0}".format(real_names))

    parent_node = Node()
    for axis_name in pseudo_names:
        axis_config = Node(parent=parent_node)
        axis_config.update({"name": axis_name, "tags": axis_name})
        axis_class = Axis
        axes.append((axis_name, axis_class, axis_config))

    name_mots = diff_name + "_motors"
    diff_mots = HKLMotors(name_mots, diff_calc, cfg_node, axes)
    diff_mots._init()
    diff_calc.calc_controller = diff_mots

    cache_dict = dict(list(zip(axes_names, [diff_mots] * len(axes_names))))
    return {diff_name: diff_calc, name_mots: diff_mots}, cache_dict


def create_object_from_cache(config, name, controller):
    try:
        return controller.get_axis(name)
    except:
        raise KeyError(name)
