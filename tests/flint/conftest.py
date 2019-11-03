# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from contextlib import contextmanager
from bliss.common import plot


def _get_real_flint(*args, **kwargs):
    """Replacement function for monkey patch of `bliss.common.plot`"""
    from bliss.flint import flint
    from silx.gui import qt

    flint.initApplication([])
    settings = qt.QSettings()
    flint_model = flint.create_flint_model(settings)
    interface = flint_model.flintApi()
    interface._pid = -666
    return interface


@contextmanager
def flint_norpc_context():
    """Context function to provide `bliss.common.plot` API without RPC.

    This allows:
    - Management of the Qt events (as Qt is part of this process)
    - Flint coverage is taken into account (as there is no side process)
    - Faster tests
    - But the RPC code ha ve to be trustable
    """
    old_get_flint = plot.get_flint
    plot.get_flint = _get_real_flint
    try:
        yield
    finally:
        plot.get_flint = old_get_flint


@pytest.fixture
def flint_norpc(xvfb, beacon):
    """Pytest fixture to provide `bliss.common.plot` API without RPC.
    """
    session = beacon.get("flint")
    session.setup()
    with flint_norpc_context():
        yield session
    session.close()
