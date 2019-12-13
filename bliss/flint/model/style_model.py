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
from typing import Optional
from typing import NamedTuple

import enum


class FillStyle(enum.Enum):
    NO_FILL = None
    SCATTER_INTERPOLATION = "scatter-interpolation"
    SCATTER_REGULAR_GRID = "scatter-regular-grid"
    SCATTER_IRREGULAR_GRID = "scatter-irregular-grid"


class LineStyle(enum.Enum):
    NO_LINE = None
    SCATTER_SEQUENCE = "scatter-sequence"


class _Style(NamedTuple):
    lineStyle: Union[None, str, LineStyle]
    lineColor: Optional[Tuple[int, int, int]]
    linePalette: Optional[int]
    symbolStyle: Optional[str]
    symbolSize: Optional[float]
    symbolColor: Optional[Tuple[int, int, int]]
    colormapLut: Optional[str]
    fillStyle: Union[None, str, FillStyle]


class Style(_Style):
    def __new__(
        cls,
        lineStyle: Union[None, str, LineStyle] = None,
        lineColor: Tuple[int, int, int] = None,
        linePalette: int = None,
        symbolStyle: str = None,
        symbolSize: float = None,
        symbolColor: Tuple[int, int, int] = None,
        colormapLut: str = None,
        fillStyle: Union[None, str, FillStyle] = None,
    ):
        try:
            lineStyle = LineStyle(lineStyle)
        except ValueError:
            pass
        try:
            fillStyle = FillStyle(fillStyle)
        except ValueError:
            pass

        return super().__new__(
            cls,
            lineStyle=lineStyle,
            lineColor=lineColor,
            linePalette=linePalette,
            symbolStyle=symbolStyle,
            symbolSize=symbolSize,
            symbolColor=symbolColor,
            colormapLut=colormapLut,
            fillStyle=fillStyle,
        )
