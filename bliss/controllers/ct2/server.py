# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
CT2 (P201 and C208) interface over the network using bliss rpc.

This requires bliss rpc and msgpack_numpy.

Usage:

    $ python -m bliss.controllers.ct2.server
    Serving ct2 on tcp://0.0.0.0:8909 ...

"""

# Imports
import sys
import os
import logging
import argparse

from bliss.comm.rpc import Server as RpcServer
from bliss.controllers.ct2 import card, device
from bliss.config.static import get_config


DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 8909
DEFAULT_CARD_TYPE = "P201"
DEFAULT_CARD_ADDRESS = "/dev/ct2_0"
DEFAULT_LOG_LEVEL = "INFO"

log = logging.getLogger("CT2Server")

"""
class CT2(device.CT2):

    def __init__(self, *args, **kwargs):
        super(CT2, self).__init__(*args, **kwargs)
        
    def get_property(self, key):
        result = getattr(self, key)
        return result

    def set_property(self, key, value):
        setattr(self, key, value)
"""


def Server(*args, **kwargs):
    server = RpcServer(*args, **kwargs)
    # set **PointNbSignal** to low latency
    server.set_low_latency_signal(device.PointNbSignal, True)
    server.set_low_latency_signal(device.StatusSignal, True)
    return server


def create_device(cfg):
    card_add = cfg["card_address"]  # make it mandatory
    card_type = cfg.get("type", DEFAULT_CARD_TYPE)
    card_cfg = {"class": card_type, "address": card_add}
    card_obj = card.create_card_from_configure(card_cfg)
    ct2dev = device.CT2(card_obj)
    ct2dev.configure(cfg)
    return ct2dev


def run(cfg):

    port = cfg.get("port", DEFAULT_PORT)
    bind = cfg.get("bind", DEFAULT_BIND)

    if cfg.get("port") is None:
        add = cfg.get("address")
        head = "tcp://"
        if add.startswith(head):
            res = add[len(head) :].split(":")
            if len(res) == 2:
                port = int(res[1])

    access = "tcp://{}:{}".format(bind, port)

    ct2dev = create_device(cfg)
    server = Server(ct2dev, stream=True)
    server.bind(access)
    log.info("Serving CT2 on {access}...".format(access=access))
    try:
        server.run()
    except KeyboardInterrupt:
        log.info("Interrupted. Bailing out!")
    finally:
        server.close()


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description="CT2 server")
    parser.add_argument("--name", type=str, help="name of the card in Beacon config")
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        type=str,
        help="log level",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
    )

    arguments = vars(parser.parse_args(args))

    obj_name = arguments["name"]
    if obj_name is None:
        raise ValueError(f"Argument '--name' is required")

    config = get_config()
    cfg = config.get_config(obj_name)
    if cfg is None:
        raise ValueError(
            f"Cannot find object '{obj_name}' on BEACON_HOST={os.getenv('BEACON_HOST')}"
        )

    log_level = arguments.pop("log_level", DEFAULT_LOG_LEVEL).upper()
    fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, log_level), format=fmt)

    run(cfg)


if __name__ == "__main__":
    main()
