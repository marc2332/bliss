from __future__ import absolute_import
import os
import sys
import pkgutil

import flask.json

from jinja2 import Environment, FileSystemLoader

from bliss.config.motors.beacon_backend import create_objects_from_config_node, create_object_from_cache
import bliss.controllers.motor as bliss_motor_controller

__KNOWN_AXIS_PARAMS = ("name", "controller", "unit", "steps_per_unit",
                       "velocity", "acceleration", "backlash",
                       "low_limit", "high_limit")

__KNOWN_CONTROLLER_PARAMS = ("name", "class", "plugin", "axes")

__this_path = os.path.realpath(os.path.dirname(__file__))


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_tree(cfg, perspective):
    if perspective == "files":
        return get_tree_files(cfg)
    elif perspective == "objects":
        return get_tree_objects(cfg)


def get_tree_files(cfg):
    ctrl_class = cfg.get("class")
    if ctrl_class is None:
        result = dict(type="axis",
                      path=os.path.join(get_tree_files(cfg.parent)['path'],
                                        cfg['name']),
                      icon="fa fa-gear")
    else:
        ctrl_name = cfg.get("name", "<unnamed controller>")
        result = dict(type="controller",
                      path=os.path.join(cfg.filename, ctrl_name),
                      icon="fa fa-gears")
    return result


def get_tree_objects(cfg):
    ctrl_class = cfg.get("class")
    if ctrl_class is None:
        result = dict(type="axis",
                      path=os.path.join(get_tree_objects(cfg.parent)['path'],
                                        cfg['name']),
                      icon="fa fa-gear")
    else:
        ctrl_name = cfg.get("name", "<unnamed controller>")
        result = dict(type="controller",
                      path=ctrl_name,
                      icon="fa fa-gears")
    return result


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
    html_template = get_jinja2().select_template([filename,
                                                  "emotion_axis.html"])

    extra_params = {}
    for key, value in vars.items():
        if key not in __KNOWN_AXIS_PARAMS:
            extra_params[key] = dict(name=key, label=key.capitalize(),
                                     value=value)

    vars["controller_class"] = ctrl_class
    if ctrl_name:
        vars["controller_name"] = ctrl_name
    vars["params"] = extra_params
    vars["units"] = cfg.get("unit", "unit")
    controllers = list()
    vars["controllers"] = controllers
    pkgpath = os.path.dirname(bliss_motor_controller.__file__)
    for _, controller_name, _ in pkgutil.iter_modules([pkgpath]):
        controllers.append({"class": controller_name})

    vars["__tango_server__"] = False
    try:
        import PyTango
        device = PyTango.DeviceProxy(name)
        vars["__tango_server__"] = device is not None
    except:
        pass

    return html_template.render(**vars)


def get_ctrl_html(cfg):
    ctrl_class = cfg.get("class")
    vars = dict(cfg.items())

    filename = "emotion_" + ctrl_class + ".html"
    html_template = get_jinja2().select_template([filename,
                                                  "emotion_controller.html"])

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

def __tango_apply_config(name):
    import PyTango.gevent
    try:
        device = PyTango.gevent.DeviceProxy(name)
        device.command_inout("ApplyConfig")
        message = "'%s' configuration saved and applied to server!" % name
        type = "success"
    except PyTango.DevFailed as df:
        message = "configuration not applied to server: " + df[0].desc
        type = "warning"
        sys.excepthook(*sys.exc_info())
    except Exception as e:
        message = "'%s' configuration saved but NOT applied to server due to error:\n%s" % (name, str(e))
        type = "warning"
        sys.excepthook(*sys.exc_info())
    return message, type

def axis_edit(cfg, request):
    if request.method == "POST":
        form = dict([(k,v) for k,v in request.form.items() if v])
        update_server = form.pop("__update_server__") == 'true'
        orig_name = form.pop("__original_name__")
        name = form["name"]
        result = dict(name=name)
        if name != orig_name:
            result["message"] = "Change of axis name not supported yet!"
            result["type"] = "danger"
            return flask.json.dumps(result)

        axis_cfg = cfg.get_config(orig_name)
        data = [(k, v) for k, v in form.iteritems()]
        axis_cfg.update(data)
        axis_cfg.save()
        if update_server:
            result["message"], result["type"] = __tango_apply_config(name)
        else:
            result["message"] = "'%s' configuration applied!" % name
            result["type"] = "success"

        return flask.json.dumps(result)
