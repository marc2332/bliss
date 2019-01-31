"""Serve the handel interface over the network using bliss rpc.

This requires python3, handel.

Usage:

    $ ./bliss-handel-server 8888
    Serving handel on tcp://0.0.0.0:8888 ...
"""

# Imports

import argparse

from bliss.comm import rpc
from bliss.controllers.mca.handel import gevent
import bliss.controllers.mca.handel.interface as hi

# Run server


def run(bind="0.0.0.0", port=8000):
    access = "tcp://{}:{}".format(bind, port)
    try:
        hi.init_handel()
        server = rpc.Server(hi)
        server.bind(access)
        print("Serving handel on {} ...".format(access))
        try:
            server.run()
        except KeyboardInterrupt:
            print("Interrupted.")
        finally:
            server.close()
    finally:
        hi.exit()


# Parsing


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog="handel-server",
        description="Serve the handel interface over the network using bliss rpc",
    )
    parser.add_argument(
        "--bind",
        "-b",
        default="0.0.0.0",
        metavar="address",
        help="Specify alternate bind address [default: all interfaces]",
    )
    parser.add_argument(
        "port",
        action="store",
        default=8000,
        type=int,
        nargs="?",
        help="Specify alternate port [default: 8000]",
    )
    return parser.parse_args(args)


# Main function


def main(args=None):
    namespace = parse_args(args)
    gevent.patch()
    run(namespace.bind, namespace.port)


if __name__ == "__main__":
    main()
