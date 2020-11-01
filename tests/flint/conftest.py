# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from contextlib import contextmanager
from bliss.flint.client import proxy
from bliss.common import plot


def _get_real_flint(*args, **kwargs):
    """Replacement function for monkey patch of `bliss.common.plot`"""
    from bliss.flint import flint
    from silx.gui import qt
    from bliss.flint.client.proxy import FlintClient

    flint.initApplication([])
    settings = qt.QSettings()
    flint_model = flint.create_flint_model(settings)

    class FlintClientMock(FlintClient):
        def _init(self, process):
            self._proxy = flint_model.flintApi()
            self._pid = -666

    return FlintClientMock()


@contextmanager
def flint_norpc_context():
    """Context function to provide `bliss.common.plot` API without RPC.

    This allows:
    - Management of the Qt events (as Qt is part of this process)
    - Flint coverage is taken into account (as there is no side process)
    - Faster tests
    - But the RPC code ha ve to be trustable
    """
    assert proxy.get_flint is plot.get_flint
    old_get_flint = proxy.get_flint
    proxy.get_flint = _get_real_flint
    plot.get_flint = _get_real_flint
    try:
        yield
    finally:
        proxy.get_flint = old_get_flint
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


@pytest.fixture
def local_flint(xvfb):
    """Registed expected things
    """
    from silx.gui import qt
    from bliss.flint import resources

    app = qt.QApplication.instance()
    if app is None:
        app = qt.QApplication([])
    resources.silx_integration()
    yield
    if app is not None:
        app.closeAllWindows()
