# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import sys
import logging
import argparse
from bliss.comm.rpc import Server
from . import card

DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 8909
DEFAULT_HEARTBEAT = 5
DEFAULT_LOG_LEVEL = "INFO"

log = logging.getLogger("FlexServer")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description="Flex server")
    parser.add_argument("name", help="flex name")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="server port")
    parser.add_argument("--bind", default=DEFAULT_BIND, type=str, help="server bind")
    parser.add_argument(
        "--heartbeat", default=DEFAULT_HEARTBEAT, type=int, help="heartbeat"
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        type=str,
        help="log level",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
    )

    arguments = vars(parser.parse_args(args))
    log_level = arguments.pop("log_level", DEFAULT_LOG_LEVEL).upper()
    fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, log_level), format=fmt)
    access = "tcp://{}:{}".format(arguments["bind"], arguments["port"])
    device_card = card.Card(arguments["name"])
    server = Server(device_card, stream=True, heartbeat=arguments["heartbeat"])
    server.bind(access)
    log.info("Serving Flex on {access}...".format(access=access))
    try:
        server.run()
    except KeyboardInterrupt:
        log.info("Interrupted. Bailing out!")
