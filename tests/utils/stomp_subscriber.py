# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
import stomp
import socket
import logging
import threading

sys.path.append(os.path.join(os.path.dirname(__file__)))
from log_utils import basic_config

logger = logging.getLogger("STOMP SUBSCRIBER")
basic_config(
    logger=logger,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class MyListener(stomp.ConnectionListener):
    def __init__(self, conn):
        self.conn = conn
        self.s_out = None
        super().__init__()

    def redirect_messages(self, port):
        if self.s_out is not None:
            self.s_out.close()
        self.s_out = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s_out.connect(("localhost", port))

    def on_message(self, header, message):
        if header.get("destination") != "/queue/icatIngest":
            return
        if self.s_out is not None:
            logger.info(f"send to output socket: {message}")
            self.s_out.sendall(message.encode() + b"\n")
        else:
            logger.info(f"received message: {message}")


def main(host=None, port=60001, queue=None, port_out=0):
    if not host:
        host = "localhost"
    if not queue:
        queue = "/queue/icatIngest"
    conn = stomp.Connection([(host, port)])
    # Listener will run in a different thread
    listener = MyListener(conn)
    conn.set_listener("", listener)
    conn.connect("guest", "guest", wait=True)
    conn.subscribe(destination=queue, id=1, ack="auto")
    logger.info(f"subscribed to {queue} on STOMP {host}:{port}")
    if port_out:
        listener.redirect_messages(port_out)
        listener.s_out.sendall(b"LISTENING\n")
    print("CTRL-C to stop")
    threading.Event().wait()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="STOMP client which subscribes to a STOMP queue and redirect its output to a TCP socket"
    )
    parser.add_argument(
        "--host", default="localhost", type=str, help="STOMP server host"
    )
    parser.add_argument("--port", default=60001, type=int, help="STOMP server port")
    parser.add_argument(
        "--queue", default="/queue/icatIngest", type=str, help="STOMP queue"
    )
    parser.add_argument("--port_out", default=0, type=int, help="output TCP socket")
    args = parser.parse_args()

    main(host=args.host, port=args.port, port_out=args.port_out, queue=args.queue)
