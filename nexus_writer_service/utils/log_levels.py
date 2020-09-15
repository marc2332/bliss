# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout De Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import logging
from tango import LogLevel, Logging

# For the TANGO loggers

tango_log_level = {
    logging.DEBUG: 600,
    logging.INFO: 500,
    logging.WARNING: 400,
    logging.ERROR: 300,
    logging.CRITICAL: 200,
    logging.NOTSET: 100,
}

itango_log_level = {v: k for k, v in tango_log_level.items()}

# For the TANGO command-line-interface

tango_cli_slog_level = {
    "DEBUG": int(LogLevel.LOG_DEBUG),
    "INFO": int(LogLevel.LOG_INFO),
    "WARNING": int(LogLevel.LOG_WARN),
    "ERROR": int(LogLevel.LOG_ERROR),
    "CRITICAL": int(LogLevel.LOG_FATAL),
    "NOTSET": int(LogLevel.LOG_OFF),
}

tango_cli_log_level = {
    logging.DEBUG: int(LogLevel.LOG_DEBUG),
    logging.INFO: int(LogLevel.LOG_INFO),
    logging.WARNING: int(LogLevel.LOG_WARN),
    logging.ERROR: int(LogLevel.LOG_ERROR),
    logging.CRITICAL: int(LogLevel.LOG_FATAL),
    logging.NOTSET: int(LogLevel.LOG_OFF),
}

itango_cli_log_level = {v: k for k, v in tango_cli_log_level.items()}

# For Beacon

beacon_log_level = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
    logging.NOTSET: "WARN",
}

ibeacon_log_level = {v: k for k, v in beacon_log_level.items()}

# For Python

log_level_name = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
    logging.NOTSET: "NOTSET",
}

ilog_level_name = {v: k for k, v in log_level_name.items()}

# Helper functions


def add_tango_cli_args(parser, default="WARNING"):
    parser.add_argument(
        "--log_tango",
        type=str.upper,
        default=default,
        help="Tango log level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
    )


def init_tango_log_level(device=None):
    """
    :param Device device:
    """
    # cli  name      core      device
    # -v1  CRITICAL  WARNING   INFO
    # -v2  ERROR     WARNING   INFO
    # -v3  WARNING   WARNING   DEBUG
    # -v4  INFO      WARNING   DEBUG
    # -v5  DEBUG     DEBUG     DEBUG
    #
    # core: DebugIt, Logit, ...
    # device: debug_stream, info_stream, ...

    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    add_tango_cli_args(parser)
    args, unknown = parser.parse_known_args()
    level = ilog_level_name[args.log_tango]
    tango_set_log_level(level, device=device)


def tango_get_log_level(device=None):
    """
    :param Device device:
    :returns int: logging.DEBUG, logging.INFO, ...
    """
    if device:
        level = device.get_logger().get_level()
    else:
        level = Logging.get_core_logger().get_level()
    return itango_log_level[level]


def tango_set_log_level(level, device=None):
    """
    :param int level: logging.DEBUG, logging.INFO, ...
    :param Device device:
    """
    level = tango_log_level[level]
    if device:
        device.get_logger().set_level(level)
    Logging.get_core_logger().set_level(level)
