# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.comm.util import get_comm, get_comm_type, TCP, GPIB, SERIAL, check_tango_fqdn


def test_get_comm_type():
    config = dict()
    with pytest.raises(ValueError):
        get_comm_type(config)

    config = dict(gpib={}, tcp={})
    with pytest.raises(ValueError):
        get_comm_type(config)

    config = dict(gpib={})
    assert get_comm_type(config) == GPIB

    config = dict(tcp={})
    assert get_comm_type(config) == TCP

    config = dict(serial={})
    assert get_comm_type(config) == SERIAL


def test_get_comm():
    config = dict()
    with pytest.raises(ValueError):
        get_comm_type(config)

    config = dict(gpib={}, tcp={})
    with pytest.raises(ValueError):
        get_comm_type(config)

    config = dict(tcp={})
    with pytest.raises(KeyError):
        get_comm(config)

    config = dict(tcp={})
    with pytest.raises(TypeError):
        get_comm(config, ctype=SERIAL)

    config = dict(tcp=dict(url="toto"))
    with pytest.raises(KeyError):
        get_comm(config)

    # should work always since tcp uses lazy connection
    tcp = get_comm(config, port=5000)
    assert tcp._host == "toto"
    assert tcp._port == 5000

    config = dict(tcp=dict(url="toto:4999"))
    tcp = get_comm(config, port=5000)
    assert tcp._host == "toto"
    assert tcp._port == 4999

    config = dict(serial=dict(url="/dev/tty0", eol=b"\r"))
    sl = get_comm(config, baudrate=38400, eol=b"\r\n")
    assert sl._port == config["serial"]["url"]
    assert sl._serial_kwargs["baudrate"] == 38400
    assert sl._eol == config["serial"]["eol"]


def test_get_comm_gpib(server_port):
    config = dict(gpib=dict(url=f"enet://localhost:{server_port}"))
    gpib = get_comm(config)
    assert gpib.gpib_type == gpib.GpibType.ENET

    config = dict(gpib=dict(url=f"prologix://localhost:{server_port}"))
    gpib = get_comm(config)
    assert gpib.gpib_type == gpib.GpibType.PROLOGIX
    gpib.open()


def test_tango_fqdn():
    assert check_tango_fqdn("12/123/as") is not None
    assert check_tango_fqdn("tango://lid21nano:20000/ID21/wcid21d/tg") is not None
    assert check_tango_fqdn("tango://ID21/wcid21d/tg") is not None
    assert check_tango_fqdn("tango://HOST/ID21/wcid21d/tg") is None
    assert check_tango_fqdn("HOST/ID21/wcid21d/tg") is None
    assert check_tango_fqdn("tango://20000/ID21/wcid21d/tg") is None
