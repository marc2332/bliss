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
from typing import Any

import enum


class DescriptiveValue(NamedTuple):
    """Allow to describe value of the enums"""

    code: Any
    name: str


class DescriptiveEnum(enum.Enum):
    @classmethod
    def fromCode(classobject, code: Any):
        for value in classobject:
            if value.value == code:
                return value
            elif isinstance(value.value, DescriptiveValue):
                if value.code == code:
                    return value
        raise ValueError(
            "Value %s not part of the enum %s" % (code, classobject.__name__)
        )

    @property
    def code(self):
        if isinstance(self.value, DescriptiveValue):
            return self.value.code
        raise AttributeError()


class FillStyle(DescriptiveEnum):
    NO_FILL = DescriptiveValue(None, "No fill")
    SCATTER_INTERPOLATION = DescriptiveValue("scatter-interpolation", "Interpolation")
    SCATTER_REGULAR_GRID = DescriptiveValue("scatter-regular-grid", "Regular grid")
    SCATTER_IRREGULAR_GRID = DescriptiveValue(
        "scatter-irregular-grid", "Irregular grid"
    )


class LineStyle(DescriptiveEnum):
    NO_LINE = DescriptiveValue(None, "No line")
    SCATTER_SEQUENCE = DescriptiveValue("scatter-sequence", "Sequence of points")


class SymbolStyle(DescriptiveEnum):
    NO_SYMBOL = DescriptiveValue(None, "No symbol")
    CIRCLE = DescriptiveValue("o", "Circle")
    PLUS = DescriptiveValue("+", "Plus")
    CROSS = DescriptiveValue("x", "Cross")
    POINT = DescriptiveValue(".", "Point")


class _Style(NamedTuple):
    lineStyle: Union[str, LineStyle]
    lineColor: Optional[Tuple[int, int, int]]
    linePalette: Optional[int]
    symbolStyle: Union[str, SymbolStyle]
    symbolSize: Optional[float]
    symbolColor: Optional[Tuple[int, int, int]]
    colormapLut: Optional[str]
    fillStyle: Union[str, FillStyle]


class Style(_Style):
    def __new__(
        cls,
        lineStyle: Union[None, str, LineStyle] = None,
        lineColor: Tuple[int, int, int] = None,
        linePalette: int = None,
        symbolStyle: Union[None, str, SymbolStyle] = None,
        symbolSize: float = None,
        symbolColor: Tuple[int, int, int] = None,
        colormapLut: str = None,
        fillStyle: Union[None, str, FillStyle] = None,
        style: Optional[Style] = None,
    ):
        if style is not None:
            if lineStyle is None:
                lineStyle = style.lineStyle
            if lineColor is None:
                lineColor = style.lineColor
            if linePalette is None:
                linePalette = style.linePalette
            if symbolStyle is None:
                symbolStyle = style.symbolStyle
            if symbolSize is None:
                symbolSize = style.symbolSize
            if symbolColor is None:
                symbolColor = style.symbolColor
            if colormapLut is None:
                colormapLut = style.colormapLut
            if fillStyle is None:
                fillStyle = style.fillStyle

        try:
            symbolStyle = SymbolStyle.fromCode(symbolStyle)
        except ValueError:
            pass

        try:
            lineStyle = LineStyle.fromCode(lineStyle)
        except ValueError:
            pass

        try:
            fillStyle = FillStyle.fromCode(fillStyle)
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


def symbol_to_silx(value: Union[None, str, SymbolStyle]):
    if value is None or value == SymbolStyle.NO_SYMBOL:
        return " "
    if isinstance(value, SymbolStyle):
        return value.code
    return str(value)
