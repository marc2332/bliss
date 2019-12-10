# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Nexus writer service for Bliss
"""

import os
from bliss.common.tango import DeviceProxy, DevFailed, Database
from tango import DbDevInfo
from .utils import logging_utils

logger = logging_utils.getLogger(__name__, __file__)


WRITER_CLASS = "NexusWriter"


def beamline():
    """
    :returns str:
    """
    name = "id00"
    for k in "BEAMLINENAME", "BEAMLINE":
        name = os.environ.get(k, name)
    return name.lower()


def find_session_writers(session_name, db=None):
    """
    Find all TANGO devices of class NexusWriter listening to a particular BLISS session.

    :param std session_name:
    :param Database db:
    :returns list(str): device names
    """
    if db is None:
        db = Database()
    writers = []
    for obj_name in db.get_device_name("*", WRITER_CLASS):
        prop = db.get_device_property(obj_name, "session")["session"]
        if prop:
            if session_name == prop[0]:
                writers.append(obj_name)
    logger.info(
        "Registered writers for session {}: {}".format(repr(session_name), writers)
    )
    return writers


def find_session_writer(session_name, db=None):
    """
    Find TANGO device of class NexusWriter listening to a particular BLISS session.

    :param std session_name:
    :param Database db:
    :returns str or None: device name
    :raises RuntimeError: more than one writer listening to session
    """
    writers = find_session_writers(session_name, db=db)
    if writers:
        if len(writers) > 1:
            raise ValueError(
                "Found more than one writer for session {}: {}".format(
                    repr(session_name), writers
                )
            )
        return writers[0]
    else:
        return None


def get_uri(p):
    return "tango://{}:{}/{}".format(p.get_db_host(), p.get_db_port(), p.dev_name())


def ensure_existence(
    session_name,
    server="nexuswriter",
    instance="nexuswriters",
    domain=None,
    family="bliss_nxwriter",
    member=None,
    use_existing=True,
):
    """
    Find or register TANGO device of class NexusWriter

    :param str session_name:
    :param str server: device server name
    :param str instance: device server instance
    :param str domain: location of device
    :param str family: type of device
    :param str member: device name (Default: `session_name`)
    :param bool use_existing: use an existing writer for this session (if any)
    :returns DeviceProxy:
    """
    db = Database()
    if not member:
        member = session_name
    if not domain():
        domain = beamline()
    dev_name = "/".join([domain, family, member])
    if use_existing:
        pdev_name = find_session_writer(session_name, db=db)
        if pdev_name:
            proxy = DeviceProxy(pdev_name)
            msg = "{} already registered".format(repr(get_uri(proxy)))
            if dev_name == pdev_name:
                logger.info(msg)
            else:
                logger.warning(msg)
            return proxy
    return register(session_name, dev_name, server=server, instance=instance)


def register(session_name, dev_name, server="nexuswriter", instance="nexuswriters"):
    """
    Register TANGO device of class NexusWriter

    :param str session_name:
    :param str dev_name: for example id00/bliss_nxwriter/test_session
    :param str instance: device server instance
    :returns DeviceProxy:
    """
    # Register proxy is not already registered
    try:
        proxy = DeviceProxy(dev_name)
        logger.info("{} already registered".format(repr(get_uri(proxy))))
    except DevFailed:
        db = Database()
        dev_info = DbDevInfo()
        dev_info.name = dev_name
        dev_info._class = WRITER_CLASS
        server = "/".join([server, instance])
        dev_info.server = server
        db.add_device(dev_info)
        proxy = DeviceProxy(dev_name)
        logger.info("{} registered".format(repr(get_uri(proxy))))
        proxy.put_property({"session": session_name})
    try:
        session = proxy.get_property("session")["session"][0]
    except (IndexError, KeyError):
        session = ""
    if session != session_name:
        raise RuntimeError(
            "{} is listening to Bliss session {} instead of {}".format(
                repr(get_uri(proxy)), repr(session), repr(session_name)
            )
        )
    return proxy


def main():
    # Define CLI
    import argparse

    parser = argparse.ArgumentParser(
        description="Register Tango device of session writing"
    )
    parser.add_argument(
        "session", type=str, default="session", help="Bliss session name"
    )
    parser.add_argument(
        "--server",
        type=str,
        default="nexuswriter",
        help="Server name ('nexuswriter' by default)",
    )
    parser.add_argument(
        "--instance",
        type=str,
        default="nexuswriters",
        help="Server instance name ('nexuswriters' by default)",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="",
        help="Device domain name (checks environment or 'id00' by default)",
    )
    parser.add_argument(
        "--family",
        type=str,
        default="bliss_nxwriter",
        help="Device family name ('bliss_nxwriter' by default)",
    )
    parser.add_argument(
        "--member", type=str, default="", help="Device name (session name by default)"
    )
    parser.add_argument(
        "--ignore_existing",
        action="store_false",
        dest="use_existing",
        help="Ignore existing writer forthis session",
    )
    logging_utils.add_cli_args(parser)
    args, unknown = parser.parse_known_args()
    ensure_existence(
        args.session,
        server=args.server,
        instance=args.instance,
        domain=args.domain,
        family=args.family,
        member=args.member,
        use_existing=args.use_existing,
    )


if __name__ == "__main__":
    main()
