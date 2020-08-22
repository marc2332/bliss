# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import logging


def basic_config(logger=None, level=None, format=None):
    """
    :param logger: root logger when not provided
    :param level: logger log level
    :param str format:
    """
    if logger is None:
        logger = logging.getLogger()
    if level is not None:
        logger.setLevel(level)
    if format:
        formatter = logging.Formatter(format)
    else:
        formatter = None

    class StdOutFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.WARNING

    class StdErrFilter(logging.Filter):
        def filter(self, record):
            return record.levelno >= logging.WARNING

    h = logging.StreamHandler(sys.stdout)
    h.addFilter(StdOutFilter())
    h.setLevel(logging.DEBUG)
    if formatter is not None:
        h.setFormatter(formatter)
    logger.addHandler(h)

    h = logging.StreamHandler(sys.stderr)
    h.addFilter(StdErrFilter())
    h.setLevel(logging.WARNING)
    if formatter is not None:
        h.setFormatter(formatter)
    logger.addHandler(h)
