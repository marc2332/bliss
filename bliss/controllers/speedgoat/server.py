# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import argparse

from bliss.comm.rpc import Server

from .speedgoat_server import Speedgoat


DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 8200


def run(url, bind=DEFAULT_BIND, port=DEFAULT_PORT):
    access = "tcp://{}:{}".format(bind, port)
    speedgoat = Speedgoat(url)
    try:
        server = Server(speedgoat)
        server.bind(access)
        print("Serving XPC speedgoat on {} ...".format(access))
        try:
            server.run()
        except KeyboardInterrupt:
            print("Interrupted.")
        finally:
            speedgoat.close_connection()
    finally:
        pass


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog="speedgoat-server",
        description="Serve the XPC speedgoat interface over the network using zerorpc",
    )
    parser.add_argument(
        "--bind",
        "-b",
        default=DEFAULT_BIND,
        metavar="address",
        help="Specify alternate bind address [default: all interfaces]",
    )
    parser.add_argument(
        "--port",
        action="store",
        default=DEFAULT_PORT,
        type=int,
        help="Specify alternate port [default: {}]".format(DEFAULT_PORT),
    )
    parser.add_argument(
        "url", help='simulink url (host:port) (ex: "192.168.7.1:22222")'
    )
    return parser.parse_args(args)


def main(args=None):
    namespace = parse_args(args)
    run(namespace.url, namespace.bind, namespace.port)


if __name__ == "__main__":
    main()
