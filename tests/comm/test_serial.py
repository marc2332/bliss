# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import time
import pytest
import gevent
import tempfile
import subprocess
import serial as pyserial
from bliss.comm import serial
from bliss.common.logtools import debugon

SOCAT = os.path.join(os.environ.get("CONDA_PREFIX", "/"), "bin", "socat")
SER2NET = os.path.join(os.environ.get("CONDA_PREFIX", "/"), "sbin", "ser2net")
RFC2217 = os.path.join(os.path.dirname(__file__), "rfc2217_server.py")

DATA = b"hello\nworld\n"


@pytest.fixture
def fake_serial():
    tempfilename = os.path.join(tempfile.gettempdir(), "fakeTty")
    tempfilename2 = os.path.join(tempfile.gettempdir(), "fakeTty2")
    fake_serial_server = subprocess.Popen(
        [
            SOCAT,
            f"pty,raw,echo=0,link={tempfilename},b9600",
            f"pty,raw,echo=0,link={tempfilename2},b9600",
        ]
    )
    gevent.sleep(1)
    yield tempfilename, tempfilename2
    fake_serial_server.terminate()


@pytest.fixture
def local_serial(fake_serial):
    tempfilename, tempfilename2 = fake_serial
    master = pyserial.Serial(tempfilename)
    slave = serial.Serial(tempfilename2)
    yield master, slave
    master.close()
    slave.close()


@pytest.fixture
def ser2net(fake_serial):
    tempfilename, tempfilename2 = fake_serial
    ser2net = subprocess.Popen(
        [SER2NET, "-n", "-u", "-p", "3332", "-C", f"3333:telnet:0:{tempfilename2}:9600"]
    )
    gevent.sleep(1)
    master = pyserial.Serial(tempfilename)
    slave = serial.Serial(f"ser2net://localhost:3332{tempfilename2}")
    yield master, slave
    master.close()
    slave.close()
    ser2net.terminate()


@pytest.fixture
def rfc2217(fake_serial):
    tempfilename, tempfilename2 = fake_serial
    rfc2217 = subprocess.Popen([sys.executable, RFC2217, f"{tempfilename2}"])
    gevent.sleep(1)
    master = pyserial.Serial(tempfilename)
    slave = serial.Serial("rfc2217://localhost:2217")
    yield master, slave
    master.close()
    slave.close()
    rfc2217.terminate()


def test_serial_comm(local_serial):
    serial_master, serial_object = local_serial

    debugon(serial_object)

    serial_object.write(DATA)
    assert serial_master.read(len(DATA)) == DATA
    serial_master.write(DATA)
    assert serial_object.read(len(DATA)) == DATA

    serial_master.write(DATA)
    assert serial_object.readline() == b"hello"
    serial_object.flush()
    serial_master.write(b"!")
    assert serial_object.read() == b"!"

    with pytest.raises(serial.SerialTimeout):
        serial_object.read(timeout=0.1)


def test_ser2net(ser2net):
    serial_master, serial_object = ser2net
    debugon(serial_object)
    ### never made this to work
    with pytest.raises(serial.SerialTimeout):
        serial_object.write(DATA)
    # assert serial_master.read(len(DATA)) == DATA
    ###
    assert serial_object._port == "rfc2217://localhost:3333"


def test_rfc2217(rfc2217):
    serial_master, serial_object = rfc2217
    debugon(serial_object)
    serial_object.write(DATA)
    assert serial_master.read(len(DATA)) == DATA
    assert serial_master.write(DATA)
    assert serial_object.read(len(DATA)) == DATA
    serial_master.write(DATA)
    assert serial_object.readline() == b"hello"
    serial_object.flush()
    serial_master.write(b"!")
    assert serial_object.read() == b"!"
    with pytest.raises(serial.SerialTimeout):
        serial_object.read(timeout=0.1)


def test_tango_serial(tango_serial):
    tg_devname, tg_device = tango_serial

    serial_object = serial.Serial(tg_devname)
    debugon(serial_object)
    serial_object.write(DATA)
    assert serial_object.readline() == b"hello"
