# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import logtools

__all__ = ["LogInitController"]


class LogInitController:
    def __init__(self, name, config):
        logtools.user_error("LogInitController: user error")
        logtools.elog_error("LogInitController: E-logbook error")
        logtools.log_error(self, "LogInitController: Beacon error")
