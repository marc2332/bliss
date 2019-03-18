# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import sys
import pkgutil
import weakref

from bliss.common import axis as axis_module
from bliss.common.axis import Axis, AxisRef
from bliss.common.encoder import Encoder
from bliss.config.static import Config, get_config
from bliss.common.tango import DeviceProxy
from bliss.config.plugins.bliss import find_class
import bliss.controllers.motors

import gevent
import hashlib
import sys


__KNOWN_AXIS_PARAMS = {
    "name": str,
    "controller": str,
    "user_tag": lambda x: x.split(","),
    "unit": str,
    "steps_per_unit": float,
    "velocity": float,
    "acceleration": float,
    "backlash": float,
    "low_limit": float,
    "high_limit": float,
}

__KNOWN_CONTROLLER_PARAMS = ("name", "class", "plugin", "axes")

__this_path = os.path.realpath(os.path.dirname(__file__))


def __get_controller_class_names():
    return bliss.controllers.motors.__all__


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        from jinja2 import Environment, FileSystemLoader

        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_item(cfg):
    klass = cfg.get("class")
    result = {"class": klass}
    if klass is None:
        result["icon"] = "fa fa-gear"
        result["type"] = "axis"
    else:
        result["icon"] = "fa fa-gears"
        result["type"] = "controller"
    return result


def get_tree(cfg, perspective):
    item = get_item(cfg)
    name = cfg.get("name")
    ctrl_class = cfg.get("class")
    if ctrl_class is None:
        path = os.path.join(get_tree(cfg.parent, "files")["path"], name)
    else:
        if perspective == "files":
            path = os.path.join(cfg.filename, name)
        else:
            path = name
    item["path"] = path
    return item


def get_html(cfg):
    ctrl_class = cfg.get("class")
    if ctrl_class is None:
        return get_axis_html(cfg)
    else:
        return get_ctrl_html(cfg)


def get_axis_html(cfg):
    name = cfg["name"]
    ctrl_class = cfg.parent.get("class")
    ctrl_name = cfg.parent.get("name")
    vars = dict(cfg.items())
    filename = "emotion_" + ctrl_class + "_axis.html"
    html_template = get_jinja2().select_template([filename, "emotion_axis.html"])

    extra_params = {}
    for key, value in vars.items():
        if key not in __KNOWN_AXIS_PARAMS:
            extra_params[key] = dict(name=key, label=key.capitalize(), value=value)

    tags = cfg.get(Config.USER_TAG_KEY, [])
    if not isinstance(tags, (tuple, list)):
        tags = [tags]
    vars["tags"] = tags
    vars["controller_class"] = ctrl_class
    if ctrl_name:
        vars["controller_name"] = ctrl_name
    vars["params"] = extra_params
    vars["units"] = cfg.get("unit", "unit")
    controllers = list()
    vars["controllers"] = controllers
    for controller_name in __get_controller_class_names():
        controllers.append({"class": controller_name})
    vars["__tango_server__"] = __is_tango_device(name)

    return html_template.render(**vars)


def get_ctrl_html(cfg):
    ctrl_class = cfg.get("class")
    vars = dict(cfg.items())

    filename = "emotion_" + ctrl_class + ".html"
    html_template = get_jinja2().select_template([filename, "emotion_controller.html"])

    extra_params = []
    for key, value in vars.items():
        if key not in __KNOWN_CONTROLLER_PARAMS:
            extra_params.append(dict(name=key, label=key.capitalize(), value=value))

    vars["params"] = extra_params
    controllers = list()
    vars["controllers"] = controllers
    pkgpath = os.path.dirname(bliss.controllers.motors.__file__)
    for _, controller_name, _ in pkgutil.iter_modules([pkgpath]):
        controllers.append({"class": controller_name})

    for axis in vars["axes"]:
        device = __is_tango_device(axis["name"])
        if device:
            vars["__tango_server__"] = True
            break
    else:
        vars["__tango_server__"] = False

    return html_template.render(**vars)


def __is_tango_device(name):
    try:
        return DeviceProxy(name) is not None
    except:
        pass
    return False


def __tango_apply_config(name):
    try:
        device = DeviceProxy(name)
        device.command_inout("ApplyConfig", True)
        msg = "'%s' configuration saved and applied to server!" % name
        msg_type = "success"
    except PyTango.DevFailed as df:
        msg = "'%s' configuration saved but <b>NOT</b> applied to " " server:\n%s" % (
            name,
            df[0].desc,
        )
        msg_type = "warning"
        sys.excepthook(*sys.exc_info())
    except Exception as e:
        msg = "'%s' configuration saved but <b>NOT</b> applied to " " server:\n%s" % (
            name,
            str(e),
        )
        msg_type = "warning"
        sys.excepthook(*sys.exc_info())
    return msg, msg_type


def controller_edit(cfg, request):
    import flask.json

    if request.method == "POST":
        form = dict([(k, v) for k, v in request.form.items() if v])
        update_server = form.pop("__update_server__") == "true"
        orig_name = form.pop("__original_name__")
        name = form.get("name", orig_name)
        result = dict(name=name)
        if name != orig_name:
            result["message"] = "Change of controller name not supported yet!"
            result["type"] = "danger"
            return flask.json.dumps(result)

        ctrl_cfg = cfg.get_config(orig_name)

        axes_data = {}
        objs = set()
        for param_name, param_value in form.items():
            if " " in param_name:  # axis param
                param_name, axis_name = param_name.split()
                obj = cfg.get_config(axis_name)
                try:
                    param_value = __KNOWN_AXIS_PARAMS[param_name](param_value)
                except KeyError:
                    pass
            else:  # controller param
                obj = ctrl_cfg
            obj[param_name] = param_value
            objs.add(obj)

        axes_server_results = {}
        for obj in objs:
            obj.save()
            if update_server and obj != ctrl_cfg:
                name = obj["name"]
                axes_server_results[name] = __tango_apply_config(name)

        msg_type = "success"
        if update_server:
            if ctrl_cfg in objs:
                msg_type = "warning"
                msg = (
                    "'%s' configuration saved! "
                    "TANGO server needs to be (re)started!" % name
                )
            else:
                msg = "'%s' configuration applied!" % name
                for axis_name, axis_result in axes_server_results:
                    msg += "<br/>" + axis_result["message"]
                    axis_msg_type = axis_result["type"]
                    if axis_msg_type != "success":
                        msg_type = axis_msg_type
        else:
            msg = "'%s' configuration applied!" % name
        result["message"] = msg
        result["type"] = msg_type
        return flask.json.dumps(result)


def axis_edit(cfg, request):
    import flask.json

    if request.method == "POST":
        form = dict([(k, v) for k, v in request.form.items() if v])
        update_server = form.pop("__update_server__") == "true"
        orig_name = form.pop("__original_name__")
        name = form["name"]
        result = dict(name=name)

        if name != orig_name:
            result["message"] = "Change of axis name not supported yet!"
            result["type"] = "danger"
            return flask.json.dumps(result)

        axis_cfg = cfg.get_config(orig_name)

        for k, v in form.items():
            try:
                v = __KNOWN_AXIS_PARAMS[k](v)
            except KeyError:
                pass
            axis_cfg[k] = v
        axis_cfg.save()
        if update_server:
            result["message"], result["type"] = __tango_apply_config(name)
        else:
            result["message"] = "'%s' configuration saved!" % name
            result["type"] = "success"
        return flask.json.dumps(result)


__ACTIONS = {
    "add": [
        {
            "id": "emotion_add_controller",
            "label": "Add controller",
            "icon": "fa fa-gears",
            "action": "plugin/emotion/add_controller",
            "disabled": True,
        },
        {
            "id": "emotion_add_axis",
            "label": "Add axis",
            "icon": "fa fa-gears",
            "action": "plugin/emotion/add_axis",
            "disabled": True,
        },
    ]
}


def actions():
    return __ACTIONS


def add_controller(cfg, request):
    if request.method == "GET":
        return flask.json.dumps(
            dict(html="<h1>TODO</h1>", message="not implemented", type="danger")
        )


def add_axis(cfg, request):
    if request.method == "GET":
        return flask.json.dumps(
            dict(html="<h1>TODO</h1>", message="not implemented", type="danger")
        )


def create_objects_from_config_node(config, node):
    if "axes" in node or "encoders" in node:
        # asking for a controller
        obj_name = None
    else:
        obj_name = node.get("name")
        node = node.parent

    controller_class_name = node.get("class")
    controller_name = node.get("name")
    if controller_name is None:
        h = hashlib.md5()
        for axis_config in node.get("axes"):
            name = axis_config.get("name")
            if name is not None:
                h.update(name.encode())
        controller_name = h.hexdigest()
    controller_class = find_class(node, "bliss.controllers.motors")
    controller_module = sys.modules[controller_class.__module__]
    axes = list()
    axes_names = list()
    encoders = list()
    encoders_names = list()
    switches = list()
    switches_names = list()
    shutters = list()
    shutters_names = list()
    for axis_config in node.get("axes"):
        axis_name = axis_config.get("name")
        if axis_name.startswith("$"):
            axis_class = AxisRef
            axis_name = axis_name.lstrip("$")
        else:
            axis_class_name = axis_config.get("class")
            if axis_class_name is None:
                axis_class = Axis
            else:
                try:
                    axis_class = getattr(axis_module, axis_class_name)
                except AttributeError:
                    axis_class = getattr(controller_module, axis_class_name)
            axes_names.append(axis_name)
        axes.append((axis_name, axis_class, axis_config))

    for objects, objects_names, default_class, default_class_name, objects_config in (
        (encoders, encoders_names, Encoder, "", node.get("encoders", [])),
        (shutters, shutters_names, None, "Shutter", node.get("shutters", [])),
        (switches, switches_names, None, "Switch", node.get("switches", [])),
    ):
        for object_config in objects_config:
            object_name = object_config.get("name")
            object_class_name = object_config.get("class")
            object_config = _checkref(config, object_config)
            if object_class_name is None:
                object_class = default_class
                if object_class is None:
                    try:
                        object_class = getattr(controller_module, default_class_name)
                    except AttributeError:
                        pass
            else:
                object_class = getattr(controller_module, object_class_name)
            objects_names.append(object_name)
            objects.append((object_name, object_class, object_config))

    controller = controller_class(
        controller_name, node, axes, encoders, shutters, switches
    )
    controller._init()

    all_names = axes_names + encoders_names + switches_names + shutters_names
    cache_dict = dict(zip(all_names, [controller] * len(all_names)))
    ctrl = cache_dict.pop(obj_name, None)
    if ctrl is not None:
        obj = create_object_from_cache(None, obj_name, controller)
        return {controller_name: controller, obj_name: obj}, cache_dict
    else:
        return {controller_name: controller}, cache_dict


def create_object_from_cache(config, name, controller):
    for func in (
        controller.get_axis,
        controller.get_encoder,
        controller.get_switch,
        controller.get_shutter,
    ):
        try:
            return func(name)
        except KeyError:
            pass
    raise KeyError(name)


def _checkref(config, cfg):
    obj_cfg = cfg.deep_copy()
    for key, value in obj_cfg.items():
        if isinstance(value, str) and value.startswith("$"):
            # convert reference to item from config
            obj = weakref.proxy(config.get(value))
            obj_cfg[key] = obj
    return obj_cfg
