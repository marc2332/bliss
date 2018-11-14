# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from tango.gevent import DeviceProxy
import pickle as pickle
import base64


def decode_tango_eval(x):
    return pickle.loads(base64.b64decode(x))


def test_2_library_instances(bliss_tango_server, s1hg, s1f, s1b, ports):
    s1hg.dial(1)
    s1hg.position(1)
    assert s1f.position() == 0.5
    assert s1b.position() == 0.5
    assert s1hg.position() == 1

    dev_name, proxy = bliss_tango_server
    tango_s1hg = DeviceProxy(
        "tango://localhost:{}/id00/bliss_test/s1hg".format(ports.tango_port)
    )

    assert tango_s1hg.read_attribute("position").value == 1
    assert tango_s1hg.read_attribute("offset").value == 0

    s1f.velocity(0.1)
    s1b.velocity(0.1)

    eval_id = proxy.eval("(s1f.velocity(), s1b.velocity())")
    gevent.sleep(0.1)
    res = proxy.get_result(eval_id)
    assert decode_tango_eval(res) == (0.1, 0.1)

    # trigger move
    tango_s1hg.position = 2

    gevent.sleep(0.1)

    assert "MOVING" in s1hg.state()

    s1hg.wait_move()

    assert s1hg.position() == pytest.approx(2)

    s1hg.rmove(1)

    value = tango_s1hg.read_attribute("position").value
    assert pytest.approx(value, 3)
