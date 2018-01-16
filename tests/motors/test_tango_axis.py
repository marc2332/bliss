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
import cPickle as pickle
import base64

def decode_tango_eval(x):
    return pickle.loads(base64.b64decode(x))

def test_2_library_instances(bliss_tango_server, s1hg, s1f, s1b):
    s1hg.dial(1); s1hg.position(1)
    assert s1f.position() == 0.5
    assert s1b.position() == 0.5
    assert s1hg.position() == 1

    dev_name, proxy = bliss_tango_server
    tango_s1hg = DeviceProxy("tango://localhost:12345/id00/bliss_test/s1hg")

    assert tango_s1hg.position == 1
    assert tango_s1hg.offset == 0
 
    s1f.velocity(0.1)
    s1b.velocity(0.1)

    eval_id = proxy.eval("(s1f.velocity(), s1b.velocity())")
    gevent.sleep(0.1)
    res = proxy.get_result(eval_id)
    assert decode_tango_eval(res) == (0.1, 0.1)

    # trigger move
    tango_s1hg.position = 2

    gevent.sleep(0.1)
 
    assert s1hg.state() == "MOVING"

    s1hg.wait_move()

    assert pytest.approx(s1hg.position(), 2)

    s1hg.rmove(1)

    assert pytest.approx(tango_s1hg.position, 3)

