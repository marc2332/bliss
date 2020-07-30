# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


try:
    from bliss.physics.backend import xraylib
except ImportError:
    xraylib = None
try:
    from bliss.physics.backend import fisx
except ImportError:
    fisx = None
try:
    from bliss.physics.backend import pymca
except ImportError:
    pymca = None

MATERIAL_BACKENDS = {"xraylib": xraylib, "fisx": fisx, "pymca": pymca}


class MaterialBackend:
    """Modify the backend used by all classes derived from this one:
        MaterialBackend.set_backend("xraylib")
    """

    _BACKEND = None

    @classmethod
    def get_backend(cls):
        if cls._BACKEND is None:
            for mod in MATERIAL_BACKENDS.values():
                if mod is not None:
                    cls._BACKEND = mod
                    break
        if cls._BACKEND is None:
            raise RuntimeError(
                f"None of the material backends are installed: {list(MATERIAL_BACKENDS.keys())}"
            )
        return cls._BACKEND

    @classmethod
    def set_backend(cls, name):
        if name not in MATERIAL_BACKENDS:
            raise ValueError(
                f"Available material backends: {list(MATERIAL_BACKENDS.keys())}"
            )
        backend = MATERIAL_BACKENDS.get(name)
        if backend is None:
            raise RuntimeError(f"Backend '{name}' not available")
        cls._BACKEND = backend
