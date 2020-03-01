# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import pytest

from bliss.controller.speedgoat import xpc


def test_lib():
    assert xpc.get_api_version() is not None
    assert xpc.get_last_error() is xpc.xpc.ENOERR
