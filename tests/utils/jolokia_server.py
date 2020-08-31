# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
import time
from datetime import datetime, timedelta
import socketserver
import logging

sys.path.append(os.path.join(os.path.dirname(__file__)))
from log_utils import basic_config

logger = logging.getLogger("JOLOKIA SERVER")
basic_config(
    logger=logger,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class MyTCPRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        request = self._read_request()
        expected_request = b"GET /api/jolokia/read/org.apache.activemq:type=Broker,brokerName=metadata,destinationType=Queue,destinationName=icatIngest/ConsumerCount"
        if expected_request in request:
            logger.info(f"Send response to {self.client_address[0]}")
            self._send_response()
        elif request:
            logger.info(f"Unknown request\n {request}")
            raise RuntimeError("Unknown request")

    def _read_request(self):
        buff = bytearray(16384)
        request = b""
        try:
            n = self.rfile.readinto1(buff)
            request = bytes(buff[0:n])
        except Exception as e:
            raise RuntimeError("Error reading request") from e
        return request

    def _send_response(self):
        now = datetime.now()
        t1 = now + timedelta(hours=5)
        out = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain;charset=UTF-8\r\nCache-Control: no-cache\r\nPragma: no-cache\r\nDate: "
            + now.strftime("%a, %d %b %Y %H:%M:%S GTM").encode()
            + b"\r\nExpires: "
            + t1.strftime("%a, %d %b %Y %H:%M:%S GTM").encode()
            + b'\r\nConnection: close\r\nServer: Jetty(7.6.9.v20130131)\r\n\r\n{"timestamp":'
            + str(int(time.time())).encode()
            + b',"status":200,"request":{"mbean":"org.apache.activemq:brokerName=metadata,destinationName=icatIngest,destinationType=Queue,type=Broker","attribute":"ConsumerCount","type":"read"},"value":6}'
        )
        self.wfile.write(out)


def main(port=8778):
    # Create a TCP Server instance
    aServer = socketserver.TCPServer(("localhost", port), MyTCPRequestHandler)

    # Listen forever
    logger.info("Starting ...")
    aServer.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TCP server which supports Jolokia (JSON over HTTP)"
    )
    parser.add_argument("--port", default=8778, type=int, help="server port")
    args = parser.parse_args()
    main(port=args.port)
