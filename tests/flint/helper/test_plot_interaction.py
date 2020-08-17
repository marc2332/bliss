"""Testing plot interaction."""

# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import pytest

from silx.gui.utils.testutils import TestCaseQt
from silx.gui.plot import Plot2D

from bliss.flint.helper import plot_interaction


@pytest.mark.usefixtures("local_flint")
class TestMaskImageSelection(TestCaseQt):
    def test_plot2d_start_stop(self):
        plot = Plot2D()
        selection = plot_interaction.MaskImageSelector(parent=plot)
        selection.start()
        selection.stop()
