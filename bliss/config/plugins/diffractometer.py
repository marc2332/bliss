# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.controllers.diffractometers import get_diffractometer_class
from bliss.controllers.motors.hklmotors import HKLMotors
from bliss.common.axis import Axis


def load_controller(controller_config):
    diff_name = controller_config["name"]
    diff_geo = controller_config.get("geometry")
    if diff_geo is None:
        raise KeyError(f"Missing diffractometer geometry in {diff_name} config")

    diff_class = get_diffractometer_class(diff_geo)
    diffracto = diff_class(diff_name, controller_config)
    return diffracto


def get_axes_info(diffracto):

    real_names = list(diffracto.axis_names)
    pseudo_names = list(diffracto.pseudo_names)

    axes = {}
    for axis_config in diffracto.config.get("axes"):
        axis_name = axis_config.get("name")
        axis_tag = axis_config.get("tags")

        # check if axes tags are valid
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

        if not isinstance(axis_name, str):
            axis_class = None
            axis_name = axis_name.name
        else:
            axis_class = Axis

        axes[axis_name] = (axis_class, axis_config)

    # check that all required reals have been found in config
    if len(real_names):
        raise KeyError("Missing real axis tags {0}".format(real_names))

    # get remaining pseudo axis not declared in config
    for axis_name in pseudo_names:
        axes[axis_name] = (Axis, {"name": axis_name, "tags": axis_name})

    return axes


def create_hkl_motors(diffracto, axes_info):
    hklmots = HKLMotors(
        f"{diffracto.name}_motors", diffracto, diffracto.config, axes_info
    )
    # --- force axis init before CalcController._init (see emotion)
    for axname in axes_info:
        hklmots.get_axis(axname)
    hklmots._init()
    return hklmots


def create_objects_from_config_node(config, cfg_node):

    controller_config = cfg_node
    is_controller = True
    if "geometry" not in cfg_node:
        is_controller = False
        controller_config = cfg_node.parent
        if "geometry" not in controller_config:  # check parent node is the controller
            raise KeyError(f"Cannot find geometry in parent node")

    diffracto = load_controller(controller_config)
    axes_info = get_axes_info(diffracto)
    hklmots = create_hkl_motors(diffracto, axes_info)

    diffracto.calc_controller = hklmots

    name2cacheditems = {axname: hklmots for axname in axes_info}
    yield {diffracto.name: diffracto}, name2cacheditems

    if not is_controller:
        obj_name = cfg_node.get("name")
        obj = config.get(obj_name)
        yield {obj_name: obj}


def create_object_from_cache(config, name, controller):
    try:
        return controller.get_axis(name)
    except:
        raise KeyError(name)
