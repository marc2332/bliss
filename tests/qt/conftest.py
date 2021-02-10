# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from silx.gui import qt


@pytest.fixture(scope="session")
def qapp(xvfb):
    app = qt.QApplication.instance()
    if app is None:
        app = qt.QApplication([])
    try:
        yield app
    finally:
        if app is not None:
            app.closeAllWindows()
