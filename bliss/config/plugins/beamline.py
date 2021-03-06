# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.config.static import ConfigNode, ConfigList
import os

import flask.json

from jinja2 import Environment, FileSystemLoader

__this_path = os.path.realpath(os.path.dirname(__file__))


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_main(cfg):
    from ..conductor.client import get_config_db_tree

    tree = get_config_db_tree()
    # if there is some configuration already
    if tree:
        return __get_main(cfg)
    else:
        return __get_empty_main(cfg)


def __get_main(cfg):
    template = get_jinja2().select_template(("beamline.html",))

    params = {}
    for k, v in cfg.root.items():
        if not isinstance(v, (ConfigList, ConfigNode)):
            params[k] = v
    logo = cfg.root.get("logo", "res/logo.png")

    html = template.render(dict(filename=cfg.root.filename, params=params, logo=logo))

    return flask.json.dumps(dict(html=html))


def __get_empty_main(cfg):
    template = get_jinja2().select_template(("empty_config.html",))
    html = template.render({})
    return flask.json.dumps(dict(html=html))


def edit(cfg, request):
    if request.method == "POST":
        for k, v in request.form.items():
            cfg.root[k] = v
    cfg.root.save()

    return flask.json.dumps(dict(message="configuration applied!", type="success"))
