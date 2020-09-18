# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import gevent
import pytest
from datetime import timedelta
from contextlib import contextmanager
from bliss.common.tango import DeviceProxy, DevState, DevFailed
from bliss.common import scans
from tests.nexus_writer.helpers import nxw_test_utils
from tests.nexus_writer.helpers import nxw_test_data


def test_nxw_tango_logging(nexus_writer_config):
    _test_nxw_tango_logging(**nexus_writer_config)


# @pytest.mark.xfail(reason="Writer is not responsive enough")
def test_nxw_tango_api(nexus_writer_config):
    _test_nxw_tango_api(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_tango_logging(writer=None, **kwargs):
    assert any(line.startswith("INFO") for line in writer.iter_stdout_lines())


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_tango_api(session=None, tmpdir=None, writer=None, **kwargs):
    scan = scans.timescan(.1, run=False)
    gscan = nxw_test_utils.run_scan(scan, runasync=True)

    # This test will check the responsiveness of the tango server.
    # This is the equivalent of having `nclients` jive panels open.
    proxy = writer.proxy
    nclients = 1
    pollinterval = 0.010
    proxy.set_timeout_millis(3000)

    print("Wait until the scan is being written ...")
    with gevent.Timeout(10):
        while proxy.state() != DevState.RUNNING:
            gevent.sleep(0.1)
        while not proxy.scan_progress:
            gevent.sleep(0.1)
        scan_name = scan.node.name
        assert proxy.scan_progress[0].startswith(f"{scan_name}: ")

    try:
        with gevent.Timeout(100):
            with poll_context(
                proxy,
                channels_have_data,
                scan_name,
                nclients=nclients,
                pollinterval=pollinterval,
            ) as glts:
                print("Poll until all channels have data ...")
                gevent.joinall(glts)
    finally:
        with gevent.Timeout(100):
            with poll_context(
                proxy,
                writer_finished,
                scan_name,
                nclients=nclients,
                pollinterval=pollinterval,
            ) as glts:
                print("Sending CTRL-C ...")
                gscan.kill(KeyboardInterrupt)
                try:
                    print("Wait for scan writer to stop ...")
                    gevent.joinall(glts)
                finally:
                    print("Wait for scan to stop ...")
                    gscan.join()

    # Verify data
    print("Verify data ...")
    while not writer_finished(proxy, scan_name):
        gevent.sleep(0.1)
    assert proxy.state() == DevState.ON
    nxw_test_data.assert_scan_data(
        scan, scan_shape=(0,), positioners=[["elapsed_time", "epoch"]], **kwargs
    )


@contextmanager
def poll_context(proxy, condition, scan_name, nclients=1, pollinterval=0):
    """Run polling in the background

    :param DeviceProxy proxy:
    :param callable condition:
    :param str scan_name: arguments to some tango calls
    :param int nclients: number of pollers
    :param num pollinterval: sleep between polling
    """
    dev_name = proxy.dev_name()
    timeout = proxy.get_timeout_millis()
    glts = [
        gevent.spawn(
            poll_writer,
            dev_name,
            timeout,
            condition,
            scan_name,
            pollinterval=pollinterval,
        )
        for _ in range(nclients)
    ]
    try:
        yield glts
    finally:
        gevent.joinall(glts)
        for g in glts:
            g.get()


def poll_writer(dev_name, timeout, condition, scan_name, pollinterval=0):
    """Poll the writer until the condition is met

    :param str dev_name:
    :param int timeout: proxy timeout
    :param callable condition:
    :param str scan_name: arguments to some tango calls
    :param num pollinterval: sleep between polling
    """
    proxy = DeviceProxy(dev_name)
    proxy.set_timeout_millis(timeout)

    tango_methods = ["state", "status", "ping"]
    tango_scan_methods = [
        "scan_state",
        "scan_uri",
        "scan_permitted",
        "scan_state_reason",
    ]
    tango_attributes = [
        "scan_states",
        "scan_uris",
        "scan_names",
        "scan_start",
        "scan_end",
        "scan_duration",
        "scan_info",
        "scan_progress",
        "scan_states_info",
    ]

    print(f"Poll {scan_name} writer ...")
    i = 0
    while not condition(proxy, scan_name):
        # print(f"\n{i}. '{condition.__name__}' condition not reached")
        # assert proxy.scan_exists(scan_name)
        # assert not proxy.scan_exists("wrong scan name")
        for attr in tango_methods:
            tango_call(proxy, attr)
        for attr in tango_scan_methods:
            tango_call(proxy, attr, scan_name)
            with pytest.raises(DevFailed):
                getattr(proxy, attr)("wrong scan name")
        for attr in tango_attributes:
            tango_getattr(proxy, attr)
        gevent.sleep(pollinterval)
        i += 1
    print(f"\n'{condition.__name__}' reached after {i} tries")


def tango_call(proxy, name, *args, **kw):
    cmd = f"{name}(*{args}, **{kw})"
    try:
        r = getattr(proxy, name)(*args, **kw)
        # print(f"{cmd} -> {r}")
    except Exception as e:
        raise RuntimeError(f"{cmd} failed") from e


def tango_getattr(proxy, name):
    try:
        r = getattr(proxy, name)
        # print(f"{name} -> {r}")
    except Exception as e:
        raise RuntimeError(f"Getting {name} failed") from e


def parse_timedelta(s):
    if "day" in s:
        m = re.match(
            r"(?P<days>[-\d]+) day[s]*, (?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d[\.\d+]*)",
            s,
        )
    else:
        m = re.match(r"(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d[\.\d+]*)", s)
    if m:
        return timedelta(**{key: float(val) for key, val in m.groupdict().items()})
    else:
        return None


def assert_delays(s):
    """Make sure the delays between Bliss and the writer are not too large
    """
    result = re.search(r"\(delay: ([^\s]+) \+ ([^\s]+)\)", s)
    delay_start = parse_timedelta(result.group(1))
    delay_writing = parse_timedelta(result.group(2))
    result = re.search(r"\(delay: ([^\s]+)\)", s)
    delay_end = parse_timedelta(result.group(1))
    dmax = timedelta(seconds=3)
    if delay_start is not None:
        err_msg = f"Delay {delay_start} between scan and writer start is too long"
        assert delay_start < dmax, err_msg
    dmax = timedelta(seconds=1)
    if delay_writing is not None:
        err_msg = f"Delay {delay_writing} between writer start and writing is too long"
        assert delay_writing < dmax, err_msg
    dmax = timedelta(seconds=10)  # TODO: too long
    if delay_end is not None:
        err_msg = f"Delay {delay_end} between scan and writer end is too long"
        assert delay_end < dmax, err_msg


def channels_have_data(proxy, scan_name, n=100):
    """Poll until all channels have data
    """
    # print(f"channels_have_data: {proxy.scan_info[0]}")
    s = proxy.scan_info[0]
    assert_delays(s)
    result = re.search(r"(\d+)pts-\d+pts", s)
    nmin = int(result.group(1))
    return nmin >= n


def writer_finished(proxy, scan_name):
    """Poll until scan writer is OFF
    """
    # print(f"writer_finished: {proxy.scan_info[0]}")
    assert_delays(proxy.scan_info[0])
    return proxy.scan_state(scan_name) == DevState.OFF
