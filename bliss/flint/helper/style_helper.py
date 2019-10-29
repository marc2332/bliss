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
from bliss.flint.model import plot_item_model


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

    _SYMBOL_SIZE = 6.0

    _COLORMAP = "viridis"

    _COLORMAPS = ["red", "green", "blue", "gray"]

    def pickColor(self, index):
        palette = self._COLOR_PALETTE
        return palette[index % len(palette)]

    def invalidateStyles(self):
        self.__cached = {}
        self.__cacheInvalidated = True

    def cacheStyle(self, item, scan, style: plot_model.Style):
        self.__cached[item, scan] = style

    def computeItemStyleFromScatterPlot(self, plot):
        scatters = []
        for item in plot.items():
            if isinstance(item, plot_item_model.ScatterItem):
                scatters.append(item)

        if len(scatters) == 1:
            scatter = scatters[0]
            style = plot_model.Style(
                symbolStyle="o",
                symbolSize=self._SYMBOL_SIZE,
                colormapLut=self._COLORMAP,
            )
            self.cacheStyle(scatter, None, style)
        else:
            baseSize = self._SYMBOL_SIZE / 3
            for i, scatter in enumerate(scatters):
                size = ((len(scatters) - 1 - i) * 2 + 2) * baseSize
                lut = self._COLORMAPS[i % len(self._COLORMAPS)]
                style = plot_model.Style(
                    symbolStyle="o", symbolSize=size, colormapLut=lut
                )
                self.cacheStyle(scatter, None, style)

    def computeItemStyleFromImagePlot(self, plot):
        images = []
        for item in plot.items():
            if isinstance(item, plot_item_model.ImageItem):
                images.append(item)

        if len(images) >= 1:
            image = images.pop(0)
            style = plot_model.Style(colormapLut=self._COLORMAP)
            self.cacheStyle(image, None, style)

        if len(images) == 1:
            baseSize = self._SYMBOL_SIZE
        else:
            baseSize = self._SYMBOL_SIZE / 2

        for i, scatter in enumerate(images):
            size = ((len(images) - 1 - i) * 2 + 1) * baseSize
            lut = self._COLORMAPS[i % len(self._COLORMAPS)]
            style = plot_model.Style(symbolStyle="o", symbolSize=size, colormapLut=lut)
            self.cacheStyle(scatter, None, style)

    def computeItemStyleFromCurvePlot(self, plot, scans):
        i = 0
        for scan in scans:
            for item in plot.items():
                if isinstance(item, plot_item_model.ScanItem):
                    continue
                if isinstance(item, plot_model.AbstractComputableItem):
                    if isinstance(item, plot_item_model.CurveStatisticMixIn):
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
                self.cacheStyle(item, scan, style)

    def computeItemStyleFromPlot(self):
        self.__cached = {}
        plot = self.plot()
        if isinstance(plot, plot_item_model.ScatterPlot):
            self.computeItemStyleFromScatterPlot(plot)
            return
        elif isinstance(plot, plot_item_model.ImagePlot):
            self.computeItemStyleFromImagePlot(plot)
            return

        scans: List[Optional[scan_model.Scan]] = []
        for item in plot.items():
            if isinstance(item, plot_item_model.ScanItem):
                scans.append(item.scan())
        if scans == []:
            scans.append(None)

        self.computeItemStyleFromCurvePlot(plot, scans)

    def getStyleFromItem(
        self, item: plot_model.Item, scan: scan_model.Scan = None
    ) -> plot_model.Style:
        if self.__cacheInvalidated:
            self.__cacheInvalidated = False
            self.computeItemStyleFromPlot()
        return self.__cached[item, scan]
