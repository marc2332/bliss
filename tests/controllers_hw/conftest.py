# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def pytest_collection_modifyitems(config, items):
    if config.getoption('--pepu') is None:
        for item in list(items):
            if 'pepu' in item.keywords:
                items.remove(item)


