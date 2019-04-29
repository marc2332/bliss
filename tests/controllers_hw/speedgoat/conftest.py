# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.controller.speedgoat import xpc


def pytest_addoption(parser):
    parser.addoption("--speedgoat", help="speedgoat url (ex: 192.168.7.1:22222)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--speedgoat") is None:
        for item in list(items):
            if "speedgoat" in item.keywords:
                items.remove(item)


@pytest.fixture(scope="session")
def speedgoat(request):
    url = request.config.getoption("--speedgoat")
    if not ":" in url:
        url += ":22222"
    goat = xpc.tcp_connect(*url.rsplit(":", 1))
    assert (
        xpc.get_app_name(goat) == "BCU_tests"
    ), "Cannot run tests if 'BCU_tests' app is not loaded"
    yield goat
    xpc.close_port(goat)
