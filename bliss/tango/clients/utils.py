# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from tango import DevFailed, DevState
from tango.gevent import DeviceProxy


def wait_tango_device(
    device_fqdn=None,
    admin=None,
    state=DevState.ON,
    wait_db=True,
    timeout=10,
    timeout_msg=None,
):
    """Wait until the tango device comes online and return a proxy.

    :param str device_fqdn: tango device URL for ping and state checking
    :param str admin: used instead of device_fqdn for ping
    :param DevState state: required tate to be considered online (default: ON)
    :param num timeout:
    :param str timeout_msg:
    :param bool wait_db: wait for the tango database to go online
    :returns DeviceProxy:
    """
    err_msg = f"Cannot create a proxy to {device_fqdn} (Tango database offline?)"
    exception = None
    try:
        with gevent.Timeout(timeout):
            # Wait until the device and optionally the database are online
            while True:
                # Check whether database is online.
                try:
                    if admin:
                        dev_proxy = DeviceProxy(admin)
                    else:
                        dev_proxy = DeviceProxy(device_fqdn)
                    if timeout_msg:
                        err_msg = timeout_msg
                    else:
                        err_msg = f"{device_fqdn} is not running"
                except DevFailed as e:
                    if wait_db:
                        exception = e
                    else:
                        raise
                else:
                    # Database is online. Now check whether the device is online.
                    try:
                        dev_proxy.ping()
                    except DevFailed as e:
                        exception = e
                    else:
                        break
                gevent.sleep(1)
            # Device and database are online. Now check the device state.
            if admin:
                dev_proxy = DeviceProxy(device_fqdn)
            if state is not None:
                if timeout_msg:
                    err_msg = f"{timeout_msg}: {device_fqdn} not in {state} state"
                else:
                    err_msg = f"{device_fqdn} not in {state} state"
                while dev_proxy.state() != state:
                    gevent.sleep(0.1)
    except gevent.Timeout:
        raise RuntimeError(err_msg) from exception
    return dev_proxy


def wait_tango_db(host=None, port=20000, db=1, timeout=10):
    """Wait until the tango database comes online and return a proxy.

    :param str host:
    :param int port:
    :param int db:
    :param num timeout:
    :returns DeviceProxy:
    """
    if host is None:
        host = "localhost"
    device_fqdn = f"tango://{host}:{port}/sys/database/{db}"
    timeout_msg = f"Tango database {device_fqdn} is not running"
    return wait_tango_device(
        device_fqdn=device_fqdn,
        timeout=timeout,
        wait_db=True,
        state=DevState.ON,
        timeout_msg=timeout_msg,
    )
