from __future__ import absolute_import
from bliss.config.motors.beacon_backend import create_objects_from_config_node, create_object_from_cache
import bliss.controllers.motor as bliss_motor_controller
from jinja2 import Environment, FileSystemLoader
import os
import pkgutil

__KNOWN_AXIS_PARAMS = ("name", "controller", "unit", "steps_per_unit",
                       "velocity", "acceleration", "backlash",
                       "low_limit", "high_limit")

__KNOWN_CONTROLLER_PARAMS = ("name", "class", "plugin", "axes")

__controllers_path = os.path.join(os.path.dirname(os.path.realpath(__file__)))

def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__controllers_path))
    return __environment


def get_html(cfg):
    ctrl_class = cfg.get("class")
    if ctrl_class is None:
        return get_axis_html(cfg)
    else:
        return get_ctrl_html(cfg)

def get_axis_html(cfg):
    ctrl_class = cfg.parent.get("class")
    ctrl_name = cfg.parent.get("name")
    vars = dict(cfg.items())

    filename = ctrl_class + "_axis.html"
    html_template = get_jinja2().select_template([filename,
                                                  "base_axis.html"])

    extra_params = []
    for key, value in vars.items():
        if key not in __KNOWN_AXIS_PARAMS:
            extra_params.append(dict(name=key, label=key.capitalize(),
                                     value=value))

    vars["controller_class"] = ctrl_class
    vars["controller_name"] = ctrl_name
    vars["params"] = extra_params
    vars["unit"] = cfg.get("unit", "units")
    vars["steps_per_unit_label"] = "Steps per " + cfg.get("unit", "unit")

    controllers = list()
    vars["controllers"] = controllers
    pkgpath = os.path.dirname(bliss_motor_controller.__file__)
    for _, controller_name, _ in pkgutil.iter_modules([pkgpath]):
        controllers.append({"class": controller_name})

    return html_template.render(**vars)

def get_ctrl_html(cfg):
    ctrl_class = cfg.get("class")
    vars = dict(cfg.items())

    html_template = get_jinja2().select_template([ctrl_class + ".html",
                                                  "base_controller.html"])

    extra_params = []
    for key, value in vars.items():
        if key not in __KNOWN_CONTROLLER_PARAMS:
            extra_params.append(dict(name=key, label=key.capitalize(),
                                     value=value))

    vars["params"] = extra_params
    controllers = list()
    vars["controllers"] = controllers
    pkgpath = os.path.dirname(bliss_motor_controller.__file__)
    for _, controller_name, _ in pkgutil.iter_modules([pkgpath]):
       controllers.append({"class": controller_name})

    return html_template.render(**vars)
