# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from bliss.common.tango import DeviceProxy, DevFailed, DevState, DevError


def find_in_exception_chain(e, cls):
    """Find the first occurance of an exception type
    in an exception chain.

    :param Exception e:
    :param Exception cls:
    :returns Exception or None: exception of type `cls`
    """
    while not isinstance(e, cls):
        try:
            e = e.__cause__
        except AttributeError:
            e = None
            break
    return e


def find_deverror(e, level):
    """Find the first occurance of `DevFailed` in an exception chain
    and return the DevError at the specifed level. Returns an empy
    `DevError` when `DevFailed` not in the exception chain.

    :param Exception e:
    :param int level:
    :returns DevError:
    """
    # https://tango-controls.github.io/cppTango-docs/except.html
    try:
        return find_in_exception_chain(e, DevFailed).args[level]
    except (AttributeError, IndexError):
        return DevError()


def is_devfailed(e):
    """`DevFailed` in the exception chain?

    :param Exception e:
    :return bool:
    """
    return find_in_exception_chain(e, DevFailed) is not None


def is_devfailed_timeout(e):
    """`DevFailed` with reason "timeout" in the exception chain?

    :param Exception e:
    :return bool:
    """
    return find_deverror(e, 1).reason == "API_DeviceTimedOut"


def is_devfailed_notallowed(e):
    """`DevFailed` with reason "not allowed" in the exception chain?

    :param Exception e:
    :return bool:
    """
    return find_deverror(e, 0).reason in ("API_AttrNotAllowed", "API_CommandNotAllowed")


def is_devfailed_reconnect_delayed(e):
    """`DevFailed` with reason "connection delayed" in the exception chain?

    :param Exception e:
    :return bool:
    """
    err = find_deverror(e, 0)
    return (
        err.reason == "API_CantConnectToDevice"
        and "The connection request was delayed" in err.desc
    )


def wait_tango_device(
    device_fqdn=None,
    admin_device_fqdn=None,
    state=DevState.ON,
    wait_db=True,
    timeout=10,
    timeout_msg=None,
):
    """Wait until the tango device comes online and return a proxy.

    :param str device_fqdn: tango device URL for ping and state checking
    :param str admin_device_fqdn: wait for this device before `device_fqdn`
    :param DevState state: required tate to be considered online (default: ON)
    :param num timeout:
    :param str timeout_msg:
    :param bool wait_db: wait for the tango database to go online
    :returns DeviceProxy:
    """
    db_err_msg = f"Cannot create a proxy to {device_fqdn} (Tango database offline?)"
    if not timeout_msg:
        timeout_msg = f"{device_fqdn} is not running"
    exception = None
    try:
        with gevent.Timeout(timeout):
            # Wait until the admin device and optionally the database are online
            if admin_device_fqdn:
                wait_tango_device(
                    device_fqdn=admin_device_fqdn,
                    wait_db=wait_db,
                    state=None,
                    timeout=None,
                    timeout_msg=f"Admin device {admin_device_fqdn} is not running",
                )
                wait_db = False

            # Wait until the device and optionally the database are online
            while True:
                # Check whether database is online.
                try:
                    dev_proxy = DeviceProxy(device_fqdn)
                except DevFailed as e:
                    err_msg = db_err_msg
                    if wait_db:
                        exception = e
                    else:
                        raise
                else:
                    # Database is online. Now check whether the device is online.
                    err_msg = timeout_msg
                    try:
                        dev_proxy.ping()
                        break
                    except DevFailed as e:
                        if not is_devfailed_reconnect_delayed(e):
                            exception = e
                            gevent.sleep(0.1)
                            continue

                    # Each DeviceProxy keeps track of the time since its last failure
                    # to connect. A connection attempt within 1 second of the last failure
                    # results in a "Reconnection delayed" exception.
                    #
                    # It seems that when DeviceProxy is instantiated, a failed connection
                    # attempt may have already happened. In this case `ping` will raise a
                    # "Reconnection delayed" exception. So sleep and try again:
                    gevent.sleep(1.1)
                    try:
                        dev_proxy.ping()
                        break
                    except DevFailed as e:
                        exception = e

            # Device and database are online. Now check the device state.
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
