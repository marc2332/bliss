import subprocess
import logging
import os
from collections import namedtuple
from pathlib import Path
import signal
import re
import time
import psutil

import shlex
import tango
import pytest
import numpy

from bliss.tango.servers import wago_ds
from bliss.controllers.wago.interlocks import register_type_to_int

"""
This is a hardware test that compare an existing WagoDS written in C++
with the Python implementation

We expect the same behaviour from the two


KNOWN ISSUES:
 * wcid31l: Log2Hard gives one different value

"""


def kill(proc_pid):
    """
    Kill a process and all its subprocesses
    """
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def getting_attributes(deviceproxy):
    """
    Retrieve a list of attributes on the device server
    """
    list_ = []
    for attr in deviceproxy.attribute_list_query():
        list_.append(attr.name)
    return list_


def wait_ds_startup(*args, timeout=20):
    start = time.time()
    dproxy = tango.DeviceProxy(*args)
    while True:
        if time.time() > start + timeout:
            raise TimeoutError
        try:
            dproxy.TurnOn()
            if dproxy.state() == tango.DevState.ON:
                return dproxy
        except (AttributeError, tango.DevFailed):
            pass
        time.sleep(.2)


def get_tango_db(timeout=10):
    """
    Waits for startup of tango db
    """
    start = time.time()
    while True:
        if time.time() > start + timeout:
            raise TimeoutError
        try:
            db = tango.Database()
            return db
        except tango.DevFailed:
            pass
        time.sleep(.5)


def isclose(val1, val2, rtol):
    comparation = numpy.isclose(val1, val2, rtol=rtol)
    if isinstance(comparation, numpy.ndarray):
        comparation = all(comparation)
    print(f"Comparing values {val1} with {val2} : {comparation}")
    return comparation


def test_isclose():
    assert isclose(5, 5.1, .1) == True
    assert isclose(5, 5.6, .1) == False
    assert isclose(-5, -5.6, .1) == False
    assert isclose(-5, -5.3, .1) == True
    assert isclose(-5, -4.3, .1) == False
    assert isclose(-5, -4.7, .1) == True
    assert isclose(0.003, 0.002, .5) == True


@pytest.fixture
def ds_environ(request, ports, beacon):
    """Compares the behaviour of an existing c++ Wago Device server
    with a created on the fly Python Wago Device Server

    Need to receive as a command line argument:
        --wago beamline_host:port,domain,plc_dns

    Example:
        --wago bibhelm:20000,ID31,wcid31c
        --wago bibhelm:20000,ID31,wcid31l
        --wago bibhelm:20000,ID31,wcid31a
        --wago bibhelm:20000,ID31,wcid31c

    Full command example:
        pytest tests/controllers_hw/test_compare_wago_ds.py --wago bibhelm:20000,ID31,wcid31f

    """
    try:
        options = request.config.getoption("--wago")
        tango_cpp_host, domain, plc_dns = options.split(",")
    except Exception:
        raise ValueError(
            "Is necessary to provide the command line option:"
            " --wago tango_cpp_host:port,domani,plc_dns\n"
            "Example: --wago bibhelm:20000,ID31,wcid31c"
        )

    tango_test_host = f"localhost:{ports.tango_port}"

    device_test_name = "unittest/wago/1"
    ds_test_instance = "wago_test_instance"

    cpp_ds_fqdn = f"tango://{tango_cpp_host}/{domain}/{plc_dns}/tg"
    py_ds_fqdn = f"tango://{tango_test_host}/{device_test_name}"

    # create device server
    cpp_ds = tango.DeviceProxy(cpp_ds_fqdn)

    modbus_dev_name = cpp_ds.get_property("modbusDevName")["modbusDevName"][0]
    modbus_ds_fqdn = f"tango://{tango_cpp_host}/{modbus_dev_name}"

    modbus_ds = tango.DeviceProxy(modbus_ds_fqdn)

    ds_file_path = str(Path(wago_ds.__file__).resolve())
    ds_name = f"{Path(wago_ds.__file__).stem}"

    # domain/family/member
    m = re.match("^[a-z0-9_-]+\/[a-z0-9_-]+\/[a-z0-9_-]+$", device_test_name)
    if not m:
        raise NameError(f"Wrong given device name {device_test_name}")

    os.environ["TANGO_HOST"] = tango_test_host

    db = get_tango_db()

    dev_info = tango.DbDevInfo()
    dev_info.server = f"{ds_name}/{ds_test_instance}"
    dev_info._class = "Wago"
    dev_info.name = device_test_name

    db.add_device(dev_info)

    py_ds = tango.DeviceProxy(py_ds_fqdn)

    # copy properties
    prop_list = cpp_ds.get_property_list("*")
    for prop in prop_list:
        p = cpp_ds.get_property(prop)
        py_ds.put_property(p)

    prop_list = modbus_ds.get_property_list("*")
    for prop in prop_list:
        p = modbus_ds.get_property(prop)
        py_ds.put_property(p)

    run_args = shlex.split(
        f"python {ds_file_path} {ds_test_instance}"
        # f"Wago {ds_test_instance}"
    )
    pro = subprocess.Popen(run_args)

    yield cpp_ds, wait_ds_startup(py_ds_fqdn)

    kill(pro.pid)

    print(f"Deleting Device {device_test_name}")
    db.delete_device(f"{device_test_name}")
    # delete class
    print(f"Deleting Device Server {dev_info.server}")
    db.delete_server(f"{dev_info.server}")


def test_wago_ds_same_attributes(ds_environ):
    cpp_ds, py_ds = ds_environ

    cpp_attrs = getting_attributes(cpp_ds)
    py_attrs = getting_attributes(py_ds)

    assert set(cpp_attrs) == set(py_attrs)


def test_wago_ds_read_attributes(ds_environ):
    cpp_ds, py_ds = ds_environ

    cpp_attrs = getting_attributes(cpp_ds)

    attrs = cpp_attrs
    attrs.remove("State")
    attrs.remove("Status")

    for attr in attrs:
        for _ in range(3):  # test multiple times because values may change
            if isclose(getattr(cpp_ds, attr), getattr(py_ds, attr), .10):
                break  # test passed

    max_key = max(py_ds.DevGetKeys())

    logical_devices = set()

    for k in range(max_key):
        assert cpp_ds.DevKey2Name(k) == py_ds.DevKey2Name(k)
        logical_devices.add(py_ds.DevKey2Name(k))

    attrs = cpp_attrs
    for name in attrs:
        assert cpp_ds.DevName2Key(name) == py_ds.DevName2Key(name)
    assert cpp_ds.read_attribute("state").value == py_ds.read_attribute("state").value
    assert cpp_ds.state() == py_ds.state()


def test_wago_ds_DevGetKeys(ds_environ):
    cpp_ds, py_ds = ds_environ

    assert str(cpp_ds.DevGetKeys()) == str(py_ds.DevGetKeys())


def test_wago_ds_DevName2Key(ds_environ):
    cpp_ds, py_ds = ds_environ

    cpp_attrs = getting_attributes(cpp_ds)

    attrs = cpp_attrs
    attrs.remove("State")
    attrs.remove("Status")

    for name in attrs:
        assert cpp_ds.DevName2Key(name) == py_ds.DevName2Key(name)


def test_wago_ds_DevKey2Name(ds_environ):
    cpp_ds, py_ds = ds_environ

    max_key = max(py_ds.DevGetKeys())
    assert max_key == max(py_ds.DevGetKeys())

    for k in range(max_key):
        assert cpp_ds.DevKey2Name(k) == py_ds.DevKey2Name(k)


def test_wago_ds_DevReadDigi(ds_environ):
    cpp_ds, py_ds = ds_environ
    logical_devices = set()

    max_key = max(py_ds.DevGetKeys())
    logical_device_keys = set(range(max_key))

    for k in range(max_key):
        assert cpp_ds.DevKey2Name(k) == py_ds.DevKey2Name(k)
        logical_devices.add(py_ds.DevKey2Name(k))

    for k in logical_device_keys:
        for _ in range(3):  # test multiple times because values change
            if isclose(cpp_ds.DevReadDigi(k), py_ds.DevReadDigi(k), .10):
                break  # test passed


def test_wago_ds_DevReadPhys(ds_environ):
    cpp_ds, py_ds = ds_environ
    logical_devices = set()

    max_key = max(py_ds.DevGetKeys())
    logical_device_keys = set(range(max_key))

    for k in range(max_key):
        assert cpp_ds.DevKey2Name(k) == py_ds.DevKey2Name(k)
        logical_devices.add(py_ds.DevKey2Name(k))

    for k in logical_device_keys:
        for _ in range(3):  # test multiple times because values change
            if isclose(cpp_ds.DevReadPhys(k), py_ds.DevReadPhys(k), .10):
                break  # test passed


def test_wago_ds_DevLog2Hard(ds_environ):
    cpp_ds, py_ds = ds_environ

    max_key = max(py_ds.DevGetKeys())
    logical_device_keys = set(range(max_key))

    for k in logical_device_keys:
        for n in range(len(cpp_ds.DevReadPhys(k))):
            assert str(cpp_ds.DevLog2Hard((k, n))) == str(py_ds.DevLog2Hard((k, n)))


def test_wago_ds_Hard2Log(ds_environ):
    cpp_ds, py_ds = ds_environ

    for io in ("IW", "IB", "OW", "OB"):
        for offset in range(0, 1000):
            try:
                cpp = cpp_ds.DevHard2Log((register_type_to_int(io), offset))
            except tango.DevFailed:
                # if cpp fails also python should faile
                with pytest.raises(tango.DevFailed):
                    pyt = cpp_ds.DevHard2Log((register_type_to_int(io), offset))
                break
            else:
                pyt = cpp_ds.DevHard2Log((register_type_to_int(io), offset))
                assert str(cpp) == str(pyt)
