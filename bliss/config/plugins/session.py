# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import collections

from .utils import find_class
from ...common.measurementgroup import MeasurementGroup


def create_objects_from_config_node(config, item_cfg_node):
    klass = find_class(item_cfg_node, "bliss.common")

    item_name = item_cfg_node["name"]
    if issubclass(klass, MeasurementGroup):
        available_counters = _get_available_counters(config, item_cfg_node)
        if available_counters != item_cfg_node.get("counters", list()):
            item_cfg_node = item_cfg_node.deep_copy()
            item_cfg_node["counters"] = available_counters

    return {item_name: klass(item_name, item_cfg_node)}


__this_path = os.path.realpath(os.path.dirname(__file__))


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        from jinja2 import Environment, FileSystemLoader

        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_item(cfg):
    from ..static import get_config
    from ..conductor.web.config_app import get_item

    config = get_config()
    items = [
        get_item(config.get_config(name)) for name in cfg.get("config-objects", ())
    ]
    result = dict(type="session", icon="fa fa-scribd", items=items)
    return result


def get_tree(cfg, perspective):
    item = get_item(cfg)
    name = cfg.get("name")
    if perspective == "files":
        path = os.path.join(cfg.filename, name)
    else:
        path = name
    item["path"] = path
    return item


def get_html(cfg):
    from ..static import get_config

    config = get_config()
    objects = cfg.get("config-objects", ())
    plugin_items = collections.defaultdict(list)
    for item_name in sorted(config.names_list):
        item_cfg = config.get_config(item_name)
        item = dict(
            name=item_name,
            checked=item_name in objects,
            description=item_cfg.get("description"),
        )
        plugin_items[item_cfg.plugin].append(item)

    params = dict(
        name=cfg["name"], setup=cfg.get("setup-file", ""), plugin_items=plugin_items
    )

    html_template = get_jinja2().select_template(["session.html"])
    return html_template.render(**params)


def edit(cfg, request):
    import flask.json

    if request.method == "POST":
        form = request.form
        orig_name = form["__original_name__"]
        name = form["name"]
        result = dict(name=name)
        if name != orig_name:
            result["message"] = "Change of card name not supported yet!"
            result["type"] = "danger"
            return flask.json.dumps(result)

        session_cfg = cfg.get_config(name)
        session_cfg["setup-file"] = form["setup"]
        session_cfg["config-objects"] = form.getlist("items[]")

        session_cfg.save()

        result["message"] = "'%s' configuration applied!" % name
        result["type"] = "success"

        return flask.json.dumps(result)


def config_objects(cfg, request):
    import flask.json

    objects = cfg.get("config-objects", ())
    return flask.json.dumps(objects)


def _get_available_counters(config, mes_grp_cfg):
    cnt_list = mes_grp_cfg.get("counters", list())
    include_list = mes_grp_cfg.get("include", list())
    for sub_grp_ref in include_list:
        sub_grp_cfg = config.get_config(sub_grp_ref)
        if sub_grp_cfg is None:
            raise RuntimeError(
                "Reference **%s** in MeasurementGroup **%s** in file %s doesn't exist"
                % (sub_grp_ref, mes_grp_cfg.get("name"), mes_grp_cfg.filename)
            )
        sub_cnt_list = _get_available_counters(config, sub_grp_cfg)
        cnt_list.extend(sub_cnt_list)
    return cnt_list
