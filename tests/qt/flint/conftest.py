# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


@pytest.fixture
def local_flint(qapp):
    """Registed expected things
    """
    from bliss.flint import resources

    resources.silx_integration()
    yield
