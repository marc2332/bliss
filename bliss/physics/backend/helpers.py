# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import enum


@enum.unique
class CrossSectionKind(enum.IntEnum):
    TOTAL = enum.auto()
    PHOTO = enum.auto()
    COHERENT = enum.auto()
    INCOHERENT = enum.auto()
    SCATTER = enum.auto()
    PAIR = enum.auto()


def get_cs_kind(kind: str):
    if kind is None:
        return kind.TOTAL
    kind = kind.lower()
    if kind in ("mass_attenuation", "total"):
        return CrossSectionKind.TOTAL
    elif kind in ("mass_absorption", "photoelectric", "photo", "pe"):
        return CrossSectionKind.PHOTO
    elif kind in ("coherent", "rayleigh"):
        return CrossSectionKind.COHERENT
    elif kind in ("incoherent", "compton"):
        return CrossSectionKind.INCOHERENT
    elif kind in ("scattering", "scatter"):
        return CrossSectionKind.SCATTER
    else:
        raise ValueError(f"Unknown cross-section {repr(kind)}")
