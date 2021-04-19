# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import logging
from collections import defaultdict
from socketserver import TCPServer
from umodbus import conf
from umodbus.server.tcp import RequestHandler, get_server

sys.path.append(os.path.join(os.path.dirname(__file__)))
from log_utils import basic_config

logger = logging.getLogger("MODBUS SERVER")
basic_config(
    logger=logger,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger.addHandler(logging.StreamHandler(sys.stdout))


def main(address):
    """
    Creates a synchronous modbus server serving 2 different memory areas
     * coils and inputs for boolean values
     * registers and holding for non boolean values

    Supported modbus functions are:
      * 1,2,3,4,5,6,15,16
    """
    regs_boolean = defaultdict(bool)  # modbus coils and inputs share the same area
    regs_boolean_size = 100
    regs_word = defaultdict(
        int
    )  # modbus input registers and holding registers shares the same area
    regs_word_size = 100

    # Enable values to be signed (default is False).
    conf.SIGNED_VALUES = True

    TCPServer.allow_reuse_address = True
    TCPServer.timeout = .1
    app = get_server(TCPServer, address, RequestHandler)

    # 1 read coil, 2 read discrete input
    @app.route(
        slave_ids=[1],
        function_codes=[1, 2],
        addresses=list(range(0, regs_boolean_size)),
    )
    def read_coils(slave_id, function_code, address):
        return regs_boolean[address]

    # 5 write coil, 15 write multiple coils
    @app.route(
        slave_ids=[1],
        function_codes=[5, 15],
        addresses=list(range(0, regs_boolean_size)),
    )
    def write_coils(slave_id, function_code, address, value):
        regs_boolean[address] = value

    # 3 read holding registers, 4 read input registers
    @app.route(
        slave_ids=[1], function_codes=[3, 4], addresses=list(range(0, regs_word_size))
    )
    def read_words(slave_id, function_code, address):
        return regs_word[address]

    @app.route(
        slave_ids=[1], function_codes=[6, 16], addresses=list(range(0, regs_word_size))
    )
    def write_words(slave_id, function_code, address, value):
        regs_word[address] = value

    logger.info("Starting ...")
    app.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Modbus TCP server")
    parser.add_argument("--port", type=int, help="server port")
    args = parser.parse_args()
    main(("127.0.0.1", args.port))
