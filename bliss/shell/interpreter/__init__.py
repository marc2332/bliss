# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
import sys


def start_interpreter(
    session_id, input_queue, output_queue, beacon_host=None, beacon_port=None
):
    interpreter = __import__("interpreter", globals(), locals(), [])

    if beacon_port is not None:
        beacon_port = int(beacon_port)

    i = interpreter.init(input_queue, output_queue, beacon_host, beacon_port)

    i.locals = setup_globals.__dict__  # .copy()

    return interpreter.start(session_id, input_queue, output_queue, i)
