# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
import re
import socket
import json
import http.server
import socketserver
import logging

sys.path.append(os.path.join(os.path.dirname(__file__)))
from log_utils import basic_config

logger = logging.getLogger("ICATPLUS SERVER")
basic_config(
    logger=logger,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger.addHandler(logging.StreamHandler(sys.stdout))


class MyTCPRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, s_out=None, **kw):
        self.s_out = s_out
        super().__init__(*args, **kw)

    def do_HEAD(self):
        logger.info("HEAD")
        self.reply_ok()

    def do_GET(self):
        logger.info("GET")
        self.reply_ok()

    def do_POST(self):
        if self.headers.get("content-type") != "application/json":
            self.reply_bad_request()
            return
        length = int(self.headers.get("content-length"))
        adict = json.loads(self.rfile.read(length))
        fmt = "/logbook/(?P<apikey>[^//]+?)/investigation/name/(?P<investigation>[^//]+?)/instrument/name/(?P<instrument>[^//]+?)/event"
        m = re.match(fmt, self.path)
        if not m:
            self.reply_bad_request()
            return
        adict.update(m.groupdict())
        self.on_message(adict)
        self.reply_ok()

    def reply_ok(self):
        self.send_response(http.HTTPStatus.OK)
        self.end_headers()

    def reply_bad_request(self):
        self.send_response(http.HTTPStatus.BAD_REQUEST)
        self.end_headers()

    def reply_json(self, adict):
        body = json.dumps(adict)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def on_message(self, adict):
        if not adict:
            return
        if self.s_out is None:
            logger.info(f"received message: {adict}")
        else:
            logger.info(f"send to output socket: {adict}")
            self.s_out.sendall(json.dumps(adict).encode() + b"\n")


def main(port=8443, port_out=0):
    if port_out:
        s_out = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_out.connect(("localhost", port_out))
    else:
        s_out = None

    class MyTCPRequestHandlerWithSocket(MyTCPRequestHandler):
        def __init__(self, *args, **kw):
            super().__init__(*args, s_out=s_out, **kw)

    # Create a TCP Server instance
    aServer = socketserver.TCPServer(("localhost", port), MyTCPRequestHandlerWithSocket)

    # Start accepting requests and setup output socket
    logger.info("Starting ...")
    if port_out:
        logger.info(f"Redirect output to {port_out}")
        s_out.sendall(json.dumps({"STATUS": "LISTENING"}).encode() + b"\n")
    aServer.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ICAT plus server")
    parser.add_argument("--port", default=8443, type=int, help="server port")
    parser.add_argument("--port_out", default=0, type=int, help="output TCP socket")
    args = parser.parse_args()
    main(port=args.port, port_out=args.port_out)
