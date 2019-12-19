# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os

import flask
import flask.json

from jinja2 import Environment, FileSystemLoader

from ..config_app.config_app import WebConfig

web_app = flask.Flask(__name__)
beacon_port = None

__this_file = os.path.realpath(__file__)
__this_path = os.path.dirname(__this_file)


__config = WebConfig()


def __get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


@web_app.route("/")
def index():
    cfg = __config.get_config()
    node = cfg.root

    template = __get_jinja2().select_template(("index.html",))

    full_name = institute = node.get("institute", node.get("synchrotron"))
    laboratory = node.get("laboratory", node.get("beamline"))
    if laboratory:
        if full_name:
            full_name += " - "
        full_name += laboratory

    beamline = node.get("beamline", "ESRF")

    return template.render(
        dict(
            name=full_name,
            beamline=beamline,
            institute=institute,
            laboratory=laboratory,
        )
    )


@web_app.route("/<dir>/<path:filename>")
def static_file(dir, filename):
    return flask.send_from_directory(os.path.join(__this_path, dir), filename)
