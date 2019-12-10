# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module provides object to model styles.
"""

from __future__ import annotations
from typing import Tuple
from typing import Union

import enum


class FillStyle(enum.Enum):
    SCATTER_INTERPOLATION = "scatter-interpolation"
    SCATTER_REGULAR_GRID = "scatter-regular-grid"


class LineStyle(enum.Enum):
    SCATTER_SEQUENCE = "scatter-sequence"


class Style:
    def __init__(
        self,
        lineStyle: Union[None, str, LineStyle] = None,
        lineColor: Tuple[int, int, int] = None,
        linePalette: int = None,
        symbolStyle: str = None,
        symbolSize: float = None,
        symbolColor: Tuple[int, int, int] = None,
        colormapLut: str = None,
        fillStyle: Union[None, str, FillStyle] = None,
    ):
        super(Style, self).__init__()
        self.__lineStyle: Union[None, str, LineStyle]
        try:
            self.__lineStyle = LineStyle(lineStyle)
        except ValueError:
            self.__lineStyle = lineStyle
        self.__lineColor = lineColor
        self.__linePalette = linePalette
        self.__symbolStyle = symbolStyle
        self.__symbolSize = symbolSize
        self.__symbolColor = symbolColor
        self.__colormapLut = colormapLut
        self.__fillStyle: Union[None, str, FillStyle]
        try:
            self.__fillStyle = FillStyle(fillStyle)
        except ValueError:
            self.__fillStyle = fillStyle

    @property
    def lineStyle(self) -> Union[None, str, LineStyle]:
        return self.__lineStyle

    @property
    def lineColor(self):
        return self.__lineColor

    @property
    def linePalette(self):
        return self.__linePalette

    @property
    def fillStyle(self) -> Union[None, str, FillStyle]:
        return self.__fillStyle

    @property
    def symbolStyle(self):
        return self.__symbolStyle

    @property
    def symbolSize(self):
        return self.__symbolSize

    @property
    def symbolColor(self):
        return self.__symbolColor

    @property
    def colormapLut(self):
        return self.__colormapLut
