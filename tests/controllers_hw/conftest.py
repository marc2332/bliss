# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.config import static
from bliss.config.conductor import client


@pytest.fixture
def beacon_beamline():
    """
    Fixture to retreive configuration objects from beamline beacon
    and not from test beacon.
    """

    static.Config.instance = None
    client._default_connection = None
    config = static.get_config()
    yield config
    config.close()
    client._default_connection.close()
    client._default_connection = None


def pytest_collection_modifyitems(config, items):
    devices = ["pepu", "ct2", "axis"]
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
