# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from bliss.common.tango import DeviceProxy, DevFailed, DevState


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
                # Sleep 1 second minimum to prevent the exception:
                #   'The connection request was delayed.
                #    Last connection request was done less than 1000 ms ago'
                gevent.sleep(1.1)
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


def wait_tango_db(host=None, port=10000, db=2, timeout=10):
    """Wait until the tango database comes online and return a proxy.
    The environment variable TANGO_HOST is never used.

    :param str host: local host by default
    :param int port:
    :param int db: typically 2 is for a test database and 1 for production
    :param num timeout:
    :returns DeviceProxy:
    """
    if host is None:
        host = "localhost"
    device_fqdn = f"tango://{host}:{port}/sys/database/{db}"
    err_msg = f"Tango database {device_fqdn} is not running"
    exception = None
    try:
        with gevent.Timeout(timeout):
            # Wait for Tango database and its admin device to come online
            dev_proxy = wait_tango_device(
                device_fqdn=device_fqdn,
                timeout=None,
                wait_db=True,
                state=DevState.ON,
                timeout_msg=err_msg,
            )
            # Wait until the database is ready
            err_msg = f"Tango database {device_fqdn} not ready"
            while True:
                try:
                    # TODO: not sure this is enough
                    dev_proxy.dbgetdeviceexportedlist("*")
                    break
                except DevFailed as e:
                    exception = e
                gevent.sleep(0.1)
    except gevent.Timeout:
        raise RuntimeError(err_msg + str(exception)) from exception
    return dev_proxy
