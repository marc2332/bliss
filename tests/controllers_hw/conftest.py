# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def pytest_collection_modifyitems(config, items):
    devices = ["pepu", "ct2"]
    for name in devices:
        try:
            if config.getoption("--%s" % name):
                continue
        except ValueError:
            continue
        # Remove device tests if no option is provided
        for item in list(items):
            if name in item.keywords:
                items.remove(item)
