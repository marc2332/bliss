# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import gevent.event
from tango.gevent import DeviceProxy
import pickle as pickle
import base64
from .conftest import wait_state


def decode_tango_eval(x):
    return pickle.loads(base64.b64decode(x))


@pytest.mark.flaky(reruns=3)
def test_2_library_instances(bliss_tango_server, s1hg, s1f, s1b, ports):
    s1hg.dial = 1
    s1hg.position = 1
    assert s1f.position == 0.5
    assert s1b.position == 0.5
    assert s1hg.position == 1

    tango_s1hg = DeviceProxy(
        "tango://localhost:{}/id00/bliss_test/s1hg".format(ports.tango_port)
    )

    assert tango_s1hg.read_attribute("position").value == 1
    assert tango_s1hg.read_attribute("offset").value == 0

    s1f.velocity = 1
    s1b.velocity = 1

    dev_name, proxy = bliss_tango_server
    eval_id = proxy.eval("(s1f.velocity, s1b.velocity)")
    res = proxy.get_result(eval_id)
    assert decode_tango_eval(res) == (1, 1)

    # Start moving
    tango_s1hg.position = 2
    wait_state(s1hg, "MOVING")

    # Check final state
    wait_state(s1hg, "READY")
    assert s1hg.position == pytest.approx(2)
    s1f.velocity = 10
    s1b.velocity = 10
    s1hg.rmove(1)

    value = tango_s1hg.read_attribute("position").value
    assert pytest.approx(value) == 3


def test_remote_stop(bliss_tango_server, robz, ports):
    robz.position = 1
    tango_robz = DeviceProxy(
        "tango://localhost:{}/id00/bliss_test/robz".format(ports.tango_port)
    )
    assert tango_robz.position == 1

    tango_robz.position = 1000
    wait_state(robz, "MOVING")

    robz.stop()
    wait_state(robz, "READY")
    assert tango_robz.position == robz.position


def test_remote_jog(bliss_tango_server, robz, ports):
    tango_robz = DeviceProxy(
        "tango://localhost:{}/id00/bliss_test/robz".format(ports.tango_port)
    )

    tango_robz.JogMove(300)
    wait_state(robz, "MOVING")

    robz.stop()
    wait_state(robz, "READY")

    tango_robz.JogMove(100)
    wait_state(robz, "MOVING")
    assert robz.jog_velocity == 100

    robz.jog(0)
    wait_state(robz, "READY")
    assert tango_robz.position == robz.position
