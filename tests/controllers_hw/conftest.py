# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.config.channels import clear_cache, Bus
from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor.client import get_default_connection


@pytest.fixture
def beacon_beamline():
    static.CONFIG = None
    client._default_connection = None
    config = static.get_config()
    connection = get_default_connection()
    yield config
    clear_cache()
    Bus.clear_cache()
    config._clear_instances()
    connection.close()
    client._default_connection = None
    static.CONFIG = None


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
