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
import subprocess
from bliss.comm import serial
import serial as pyserial

# from bliss.common.logtools import debugon
import socket
from contextlib import contextmanager
import yaml
from bliss.common.utils import deep_update

SOCAT = os.path.join(os.environ.get("CONDA_PREFIX", "/"), "bin", "socat")
SER2NET = os.path.join(os.environ.get("CONDA_PREFIX", "/"), "sbin", "ser2net")


@pytest.fixture(scope="session")
def find_free_port():
    """
    Returns a factory that finds the next free port that is available on the OS
    This is a bit of a hack, it does this by creating a new socket, and calling
    bind with the 0 port. The operating system will assign a brand new port,
    which we can find out using getsockname(). Once we have the new port
    information we close the socket thereby returning it to the free pool.
    This means it is technically possible for this function to return the same
    port twice (for example if run in very quick succession), however operating
    systems return a random port number in the default range (1024 - 65535),
    and it is highly unlikely for two processes to get the same port number.
    In other words, it is possible to flake, but incredibly unlikely.
    """

    # taken from https://gist.github.com/bertjwregeer/freeport.py

    def _find_free_port():
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 0))
        portnum = s.getsockname()[1]
        s.close()

        return portnum

    return _find_free_port


def _inspect_serial_port_settings(fake_port):

    serial_port_fd, ref_socket_port = fake_port

    sp = subprocess.Popen(
        ["stty", "--all", f"--file={serial_port_fd}"], stdout=subprocess.PIPE
    )
    out, err = sp.communicate()

    options = {}
    params = []

    out = out.decode()

    for s in out.split("\n"):
        if ";" in s:
            tmp = (
                "{'"
                + s.replace("; ", ";")
                .replace(";", ",")
                .replace(" baud,", ",")
                .replace(" = ", " ")
                .strip(",")
                .replace(",", "','")
                .replace(" ", "':'")
                + "'}"
            )
            deep_update(options, yaml.load(tmp, Loader=yaml.Loader))
        else:
            params += yaml.load("['" + s.replace(" ", "','") + "']", Loader=yaml.Loader)
    return (options, params)


@pytest.fixture(scope="session")
def fake_serial(find_free_port):
    ref_socket_port = find_free_port()

    fake_serial_server = subprocess.Popen(
        [SOCAT, "-d", "-d", "pty,rawer", f"tcp-listen:{ref_socket_port},fork"],
        stderr=subprocess.PIPE,
    )

    gevent.sleep(1)

    err = fake_serial_server.stderr.readline()
    err = err.strip()
    err = err.decode()
    serial_port_fd = err.split(" ")[-1]

    print("Emulated serial port:", serial_port_fd)
    print("Reference socket port:", ref_socket_port)

    yield serial_port_fd, ref_socket_port
    fake_serial_server.terminate()


@pytest.fixture
def reference_socket(fake_serial):
    serial_port_fd, ref_socket_port = fake_serial
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soc.connect(("localhost", ref_socket_port))

    # empty socket in case there was anything send into the port
    # before socket creation
    soc.settimeout(.01)
    try:
        soc.recv(1000)
    except socket.timeout:
        pass
    soc.settimeout(.1)
    yield soc
    soc.close()


@pytest.fixture(scope="session")
def ser2net_server(find_free_port, fake_serial):
    serial_port_fd, ref_socket_port = fake_serial
    s2n_control_port = find_free_port()
    s2n_port_telnet = find_free_port()
    s2n_port_raw = find_free_port()
    s2n_port_raw_nobreak = find_free_port()

    s2nconf = (
        f"{s2n_port_telnet}:telnet:0:{serial_port_fd}:9600 remctl kickolduser\n"
        f"{s2n_port_raw}:raw:0:{serial_port_fd}:9600 remctl kickolduser\n"
        f"{s2n_port_raw_nobreak}:raw:0:{serial_port_fd}:9600 remctl kickolduser NOBREAK\n"
    )

    ser2net = subprocess.Popen(
        [SER2NET, "-n", "-u", "-p", str(s2n_control_port), "-C", s2nconf]
    )

    gevent.sleep(1)

    yield s2n_control_port, s2n_port_telnet, s2n_port_raw, s2n_port_raw_nobreak, serial_port_fd

    ser2net.terminate()


@pytest.fixture
def local_serial(fake_serial):
    @contextmanager
    def _local_serial(params={}):
        serial_port_fd, ref_socket_port = fake_serial
        try:
            serial_port = serial.Serial(serial_port_fd, **params)
            gevent.sleep(.5)
            yield serial_port
        finally:
            print("close local")
            serial_port.close()

    return _local_serial


# mainly for test debugging
@pytest.fixture
def local_pyserial(fake_serial):
    @contextmanager
    def _local_pyserial(params={}):
        serial_port_fd, ref_socket_port = fake_serial
        try:
            serial_port = pyserial.Serial(serial_port_fd, **params)
            gevent.sleep(.5)
            yield serial_port
        finally:
            print("close local pyserial")
            serial_port.close()

    return _local_pyserial


@pytest.fixture
def ser2net_telnet(ser2net_server):
    @contextmanager
    def _ser2net_telnet(params={}):
        s2n_control_port, s2n_port_telnet, s2n_port_raw, s2n_port_raw_nobreak, serial_port_fd = (
            ser2net_server
        )
        try:
            serial_port = serial.Serial(
                f"ser2net://localhost:{s2n_control_port}{serial_port_fd}", **params
            )
            gevent.sleep(.5)
            # TODO: Why is this sleep needed?
            # if it is real and not just due to the test the sleep should
            # rather be inside the init of serial.Serial, shouldn't it?
            yield serial_port
        finally:
            print("close ser2net")
            serial_port.close()

    return _ser2net_telnet


@pytest.fixture
def rfc2217_telnet(ser2net_server):
    @contextmanager
    def _rfc2217_telnet(params={}):
        s2n_control_port, s2n_port_telnet, s2n_port_raw, s2n_port_raw_nobreak, serial_port_fd = (
            ser2net_server
        )
        try:
            serial_port = serial.Serial(
                f"rfc2217://localhost:{s2n_port_telnet}", **params
            )
            gevent.sleep(.5)
            # TODO: Why is this sleep needed?
            # if it is real and not just due to the test the sleep should
            # rather be inside the init of serial.Serial, shouldn't it?
            yield serial_port
        finally:
            print("close rfc")
            serial_port.close()

    return _rfc2217_telnet


@pytest.fixture
def get_serial(request):
    return request.getfixturevalue(request.param)


PARAMS_1 = {
    "baudrate": 19200,
    "bytesize": pyserial.SEVENBITS,
    "stopbits": serial.STOPBITS_TWO,
}
PARAMS_2 = {
    "baudrate": 38400,
    "bytesize": pyserial.SEVENBITS,
    "parity": pyserial.PARITY_ODD,
    "xonxoff": True,
}
PARAMS_3 = {
    "baudrate": 38400,
    "bytesize": pyserial.SEVENBITS,
    "parity": pyserial.PARITY_EVEN,
    "rtscts": True,
}


ALL_PORTS = [
    ("ser2net_telnet", {}),
    ("ser2net_telnet", PARAMS_1),
    ("ser2net_telnet", PARAMS_2),
    ("ser2net_telnet", PARAMS_3),
    ("rfc2217_telnet", {}),
    ("rfc2217_telnet", PARAMS_1),
    ("rfc2217_telnet", PARAMS_2),
    ("rfc2217_telnet", PARAMS_3),
    ("local_serial", {}),
    ("local_serial", PARAMS_1),
    ("local_serial", PARAMS_2),
    ("local_serial", PARAMS_3),
    # for debugging of tests
    ("local_pyserial", {}),
    ("local_pyserial", PARAMS_1),
    ("local_pyserial", PARAMS_2),
    ("local_pyserial", PARAMS_3),
]

EOL_PORTS = [
    ("ser2net_telnet", {}),
    ("rfc2217_telnet", {}),
    ("local_serial", {}),
    ("ser2net_telnet", {"eol": b"\r\n"}),
    ("rfc2217_telnet", {"eol": b"\r\n"}),
    ("local_serial", {"eol": b"\r\n"}),
]

SIMPLE_PORTS = [("ser2net_telnet", {}), ("rfc2217_telnet", {}), ("local_serial", {})]


@pytest.mark.parametrize("get_serial,params", ALL_PORTS, indirect=["get_serial"])
def test_serial_write_ascii(get_serial, params, reference_socket):
    with get_serial(params) as serial_port:
        data = b"hello\nworld\n"
        serial_port.write(data)
        assert reference_socket.recv(1000) == data


@pytest.mark.parametrize("get_serial,params", ALL_PORTS, indirect=["get_serial"])
def test_serial_read_ascii(get_serial, params, reference_socket):
    with get_serial(params) as serial_port:
        data = b"hello\nworld\n"
        serial_port.write(b"bla")
        reference_socket.send(data)
        assert serial_port.read(len(data)) == data


@pytest.mark.parametrize("get_serial,params", EOL_PORTS, indirect=["get_serial"])
def test_serial_write_readline_ascii(get_serial, params, reference_socket):
    with get_serial(params) as serial_port:
        eol = b"\n"
        if "eol" in params:
            eol = params["eol"]
        data = b"hello" + eol + b"bla"
        data2 = b"world" + eol + b"bla" + eol

        g = gevent.spawn(serial_port.write_readline, data)
        gevent.sleep(.1)
        reference_socket.send(data2)
        assert reference_socket.recv(1000) == data
        assert g.get() == b"world"
        assert serial_port.readline() == b"bla"

        g = gevent.spawn(serial_port.write_readline, data, eol="#")
        gevent.sleep(.1)
        reference_socket.send(b"blub#blub")
        assert reference_socket.recv(1000) == data
        assert g.get() == b"blub"


@pytest.mark.parametrize("get_serial,params", EOL_PORTS, indirect=["get_serial"])
def test_serial_write_read_single_char(get_serial, params, reference_socket):
    with get_serial(params) as serial_port:

        eol = b"\n"
        if "eol" in params:
            eol = params["eol"]

        serial_port.write(b"1")
        assert reference_socket.recv(1000) == b"1"
        reference_socket.send(b"2")
        assert serial_port.raw_read(1) == (b"2")

        serial_port.write(b"\n")
        assert reference_socket.recv(1000) == b"\n"
        reference_socket.send(b"\n")
        assert serial_port.raw_read(1) == (b"\n")


@pytest.mark.parametrize("get_serial,params", SIMPLE_PORTS, indirect=["get_serial"])
def test_serial_IAC(get_serial, params, reference_socket):
    with get_serial(params) as serial_port:
        IAC = bytes([0xFF])
        serial_port.write(IAC)
        assert reference_socket.recv(1000) == IAC
        reference_socket.send(IAC)
        assert serial_port.raw_read(1) == IAC

        doubel_iac = IAC + IAC + b"bla"
        reference_socket.send(doubel_iac)
        assert serial_port.read(5) == doubel_iac

        reference_socket.send(doubel_iac)
        assert serial_port.raw_read(5) == doubel_iac


@pytest.mark.parametrize("get_serial,params", SIMPLE_PORTS, indirect=["get_serial"])
def test_raw_write_read(get_serial, params, reference_socket):
    # waiting for ser2net v4
    pytest.xfail()

    with get_serial(params) as serial_port:
        tmp = list(range(0, 256))
        IAC = bytes([0xFF])
        all_chars = (
            bytes(tmp) + bytes(tmp[::-1]) + IAC + b"#" + IAC + IAC + IAC + b"#" + IAC
        )

        serial_port.write(all_chars)
        gevent.sleep(.1)
        ans1 = reference_socket.recv(len(all_chars))
        assert ans1 == all_chars

        reference_socket.send(all_chars)
        gevent.sleep(.1)
        ans2 = serial_port.raw_read(len(all_chars))
        assert ans2 == all_chars


@pytest.mark.parametrize("get_serial,params", SIMPLE_PORTS, indirect=["get_serial"])
def test_raw_write_read2(get_serial, params, reference_socket):
    # waiting for ser2net v4
    pytest.xfail()

    with get_serial(params) as serial_port:
        tmp = list(range(0, 256))
        IAC = bytes([0xFF])
        all_chars = (
            bytes(tmp) + bytes(tmp[::-1]) + IAC + b"#" + IAC + IAC + IAC + b"#" + IAC
        )
        all_chars2 = IAC + all_chars

        serial_port.write(all_chars2)
        gevent.sleep(.1)
        ans1 = reference_socket.recv(len(all_chars2))
        assert ans1 == all_chars2

        reference_socket.send(all_chars2)
        gevent.sleep(.1)
        ans2 = serial_port.raw_read(len(all_chars2))
        assert ans2 == all_chars2


@pytest.mark.parametrize("get_serial,params", ALL_PORTS, indirect=["get_serial"])
def test_serial_port_settings(get_serial, params, reference_socket, fake_serial):

    with get_serial(params) as (serial_port):

        # do something with the port
        data = b"hello\nworld\n"
        serial_port.write(data)

        options, parameters = _inspect_serial_port_settings(fake_serial)

        # check baudrate
        if "baudrate" in params:
            assert options["speed"] == str(params["baudrate"])
        else:
            assert options["speed"] == "9600"

        # check bytesize
        # hmm cs8 always set... limitation of socat?

        # check parity
        if "parity" not in params or params["parity"] != pyserial.PARITY_ODD:
            assert "-parodd" in parameters
        else:
            assert "parodd" in parameters

        # check stopbits
        if "stopbits" not in params or params["stopbits"] == pyserial.STOPBITS_ONE:
            assert "-cstopb" in parameters
        else:
            assert "cstopb" in parameters

        # check xonxoff
        if "xonxoff" not in params or params["xonxoff"] == False:
            assert "-ixon" in parameters
            assert "-ixoff" in parameters
        else:
            assert "ixon" in parameters
            assert "ixoff" in parameters

        # check rtscts
        if "rtscts" not in params or params["rtscts"] == False:
            assert "-crtscts" in parameters
        else:
            assert "crtscts" in parameters

        # check dsrdtr
        # hmm, how to check?

        print(options)
        print(parameters)


### tango tests are by far not complete ... come back to this once we have a real serial tango serial server
def test_tango_serial(tango_serial):
    tg_devname, tg_device = tango_serial

    serial_object = serial.Serial(tg_devname)
    serial_object.write(b"hello")
    assert serial_object.readline() == b"world"


### to be seen with ser2net 4 it this test make any sense

TROUBLE_PARAMS = {"rtscts": True, "xonxoff": True}

TROUBLE_PORTS = [
    ("ser2net_telnet", {}),
    (
        "ser2net_telnet",
        TROUBLE_PARAMS,
    ),  # these parameters let the ser2net server or the emulated port struggle
    ("rfc2217_telnet", {}),
    (
        "rfc2217_telnet",
        TROUBLE_PARAMS,
    ),  # these parameters let the ser2net server or the emulated port struggle
    ("local_serial", {}),
    ("local_serial", TROUBLE_PARAMS),
    # for debugging of tests
    ("local_pyserial", {}),
    ("local_pyserial", TROUBLE_PARAMS),
]
# TODO: seems like there is a problem with specifying options via ser2net and rfc2217
# ... is this real or only due to the emulated port


@pytest.mark.parametrize("get_serial,params", TROUBLE_PORTS, indirect=["get_serial"])
def test_serial_write_ascii_trouble(get_serial, params, reference_socket):
    pytest.xfail()
    with get_serial(params) as serial_port:
        data = b"hello\nworld\n"
        serial_port.write(data)
        assert reference_socket.recv(1000) == data
