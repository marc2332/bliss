# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os

from bliss.controllers.ct2 import card, create_objects_from_config_node

# low level card gui (probably for developers only)
from . import _ct2

from bliss.common.utils import OrderedDict

__this_path = os.path.dirname(os.path.realpath(__file__))


def get_jinja2():
    from jinja2 import Environment, FileSystemLoader

    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_item(cfg):
    klass = cfg.get("class")
    if klass != "CT2":
        return _ct2.get_item(cfg)
    return {"class": klass, "icon": "fa fa-credit-card", "type": "Counter device"}


def get_tree(cfg, perspective):
    if cfg.get("class") != "CT2":
        return _ct2.get_tree(cfg, perspective)
    return dict(
        type="Counter device",
        path=os.path.join(cfg.filename, cfg["name"]),
        icon="fa fa-credit-card",
    )


def get_html(cfg):
    if cfg.get("class") != "CT2":
        return _ct2.get_html(cfg)
    return get_device_html(cfg)


def get_device_html(cfg):
    config = dict(list(cfg.items()))
    config["filename"] = cfg.filename
    card_type = config.setdefault("type", "P201")
    config.setdefault("clock", "CLK_100_MHz")
    config.setdefault("address", "")
    ext_sync = config.setdefault("external sync", {})
    inp = ext_sync.setdefault("input", {"polarity inverted": False})
    out = ext_sync.setdefault("output", {})
    card_class = card.get_ct2_card_class(card_type)

    card_channels = dict([(ch["address"], ch) for ch in config.get("channels", [])])

    config["channels"] = channels = []
    for addr in card_class.CHANNELS:
        channel = {"address": addr, "level": "TTL", "50 ohm": False}
        channel.update(card_channels.get(addr, {}))
        channels.append(channel)
    params = dict(card=card, klass=card_class, config=config)
    html_template = get_jinja2().select_template(["ct2.html"])
    return html_template.render(**params)


from ._ct2 import card_edit


def __update_config_value(config, name, value):
    if value in (None, ""):
        if name in config:
            del config[name]
    else:
        config[name] = value


def device_edit(cfg, request):
    import flask.json

    if request.method != "POST":
        return

    form = request.form
    orig_card_name = form.get("__original_name__")
    card_name = form["device-name"]
    if card_name != orig_card_name:
        result["message"] = "Change of card name not supported yet!"
        result["type"] = "danger"
        return flask.json.dumps(result)

    card_cfg = cfg.get_config(orig_card_name)

    card_type = form["device-type"]
    card_class = card.get_ct2_card_class(card_type)

    external_sync = {}

    channels = []
    for addr in card_class.CHANNELS:
        prefix = "ch-{0}-".format(addr)
        channel = {}
        level = form.get(prefix + "level", "TTL")
        counter_name = form.get(prefix + "counter-name")
        ohm = form.get(prefix + "50-ohm", "off") == "on"
        usage = int(form.get(prefix + "usage", "0"))
        channel["level"] = level
        channel["50 ohm"] = ohm
        if counter_name:
            channel["counter name"] = counter_name
        if usage == 1:
            inp = external_sync.setdefault("input", {})
            inp["channel"] = addr
            inp["polarity inverted"] = False
        elif usage == 2:
            inp = external_sync.setdefault("input", {})
            inp["channel"] = addr
            inp["polarity inverted"] = True
        elif usage == 3:
            out = external_sync.setdefault("output", {})
            out["channel"] = addr
        if channel:
            channel["address"] = addr
            channels.append(channel)

    result = {
        "name": card_name,
        "type": card_type,
        "class": "CT2",
        "address": form["device-address"],
        "clock": form["device-clock"],
        "channels": channels,
        "external sync": external_sync,
    }

    card_cfg.update(result)  # [(k, v) for k, v in cfg.items()])
    card_cfg.save()

    result["message"] = "'%s' configuration applied!" % card_name
    result["type"] = "success"

    return flask.json.dumps(result)
