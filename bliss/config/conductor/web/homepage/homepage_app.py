# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import flask

from jinja2 import Environment, FileSystemLoader

# from ..configuration.config_app import WebConfig
from bliss.config import static


__this_file = os.path.realpath(__file__)
__this_path = os.path.dirname(__this_file)
# __config = WebConfig()


def __get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


web_app = flask.Flask(__name__)


@web_app.route("/")
def index():
    # cfg = __config.get_config()
    cfg = static.get_config()
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


#
# Redirections to other web applications
# (so that we don't need to remember all ports)
#
@web_app.route("/configuration/")
@web_app.route("/config/")
def config():
    host = flask.request.host.split(":")[0]
    return flask.redirect(f"http://{host}:{web_app.config_port}")


@web_app.route("/multivisor/")
@web_app.route("/status/")
def multivisor():
    host = flask.request.host.split(":")[0]
    return flask.redirect(f"http://{host}:22000")


@web_app.route("/supervisor/")
def supervisor():
    host = flask.request.host.split(":")[0]
    return flask.redirect(f"http://{host}:9001")


@web_app.route("/log/")
@web_app.route("/logs/")
def log_viewer():
    host = flask.request.host.split(":")[0]
    return flask.redirect(f"http://{host}:{web_app.log_port}")
