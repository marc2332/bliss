# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Helper functions to deal with style
"""

from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple

from bliss.flint.model import scan_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model


class DefaultStyleStrategy(plot_model.StyleStrategy):
    def __init__(self):
        super(DefaultStyleStrategy, self).__init__()
        self.__cached: Dict[
            Tuple[plot_model.Item, Optional[scan_model.Scan]], plot_model.Style
        ] = {}
        self.__cacheInvalidated = True

    _COLOR_PALETTE = [
        (87, 81, 212),
        (235, 171, 33),
        (176, 69, 0),
        (0, 197, 248),
        (207, 97, 230),
        (0, 166, 107),
        (184, 0, 87),
        (0, 138, 248),
        (0, 110, 0),
        (0, 186, 171),
        (255, 145, 133),
        (133, 133, 0),
    ]

    def pickColor(self, index):
        palette = self._COLOR_PALETTE
        return palette[index % len(palette)]

    def invalidateStyles(self):
        self.__cached = {}
        self.__cacheInvalidated = True

    def computeItemStyleFromPlot(self):
        self.__cached = {}
        plot = self.plot()

        scans: List[Optional[scan_model.Scan]] = []
        for item in plot.items():
            if isinstance(item, plot_curve_model.ScanItem):
                scans.append(item.scan())
        if scans == []:
            scans.append(None)

        i = 0
        for scan in scans:
            for item in plot.items():
                if isinstance(item, plot_curve_model.ScanItem):
                    continue
                if isinstance(item, plot_model.AbstractComputableItem):
                    if isinstance(item, plot_curve_model.CurveStatisticMixIn):
                        source = item.source()
                        baseStyle = self.getStyleFromItem(source, scan)
                        style = plot_model.Style(
                            lineStyle=":", lineColor=baseStyle.lineColor
                        )
                    else:
                        source = item.source()
                        baseStyle = self.getStyleFromItem(source, scan)
                        style = plot_model.Style(
                            lineStyle="-.", lineColor=baseStyle.lineColor
                        )
                else:
                    color = self.pickColor(i)
                    style = plot_model.Style(lineStyle="-", lineColor=color)
                    i += 1
                self.__cached[item, scan] = style

    def getStyleFromItem(
        self, item: plot_model.Item, scan: scan_model.Scan = None
    ) -> plot_model.Style:
        if self.__cacheInvalidated:
            self.__cacheInvalidated = False
            self.computeItemStyleFromPlot()
        return self.__cached[item, scan]
