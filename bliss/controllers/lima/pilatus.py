# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import tabulate

from .properties import LimaProperty
from .lima_base import CameraBase

# HWROIS definition : (x0, y0, width, height, max_rate)
HWROIS = {
    "PILATUS3 6M": {
        "FULL": (0, 0, 2463, 2526, 100),
        "C2": (988, 1060, 487, 407, 200),
        "C18": (494, 636, 1475, 1255, 500),
    },
    "PILATUS3 2M": {
        "FULL": (0, 0, 1475, 1679, 250),
        "C12": (0, 424, 1475, 831, 250),
        "R8": (494, 424, 981, 831, 500),
        "L8": (0, 424, 981, 831, 500),
        "C2": (494, 636, 487, 407, 500),
    },
    "PILATUS3 1M": {
        "FULL": (0, 0, 981, 1043, 500),
        "R1": (494, 424, 487, 195, 500),
        "L1": (0, 424, 487, 195, 500),
        "R3": (494, 212, 487, 619, 500),
        "L3": (0, 212, 487, 619, 500),
    },
    "PILATUS2 6M": {
        "FULL": (0, 0, 2463, 2526, 100),
        "C2": (988, 1060, 487, 407, 200),
        "C18": (494, 636, 1475, 1255, 500),
    },
}


class Camera(CameraBase):
    def __init__(self, name, lima_device, proxy):
        self.name = name
        self._proxy = proxy
        self._lima_proxy = lima_device.proxy
        self._model = None

    def __find_model(self):
        try:
            model = self._lima_proxy.camera_model
        except:
            return None
        try:
            back_roi = self._lima_proxy.image_roi
            self._lima_proxy.image_roi = (0, 0, 0, 0)
            img_size = tuple(self._lima_proxy.image_sizes[2:4])
            self._lima_proxy.image_roi = back_roi
        except:
            return None

        if model.find("PILATUS3") == 0:
            if img_size == (2463, 2527):
                return "PILATUS3 6M"
            if img_size == (1475, 1679):
                return "PILATUS3 2M"
            if img_size == (981, 1043):
                return "PILATUS3 1M"
            return "PILATUS3"
        else:
            if img_size == (2463, 2527):
                return "PILATUS2 6M"
            return "PILATUS2"

    def __get_hwrois(self):
        model = self.model
        if model not in HWROIS.keys():
            raise RuntimeError("HW ROIS not defined for model [{0}]".format(model))
        return HWROIS[model]

    def hwroi_list(self):
        hwrois = self.__get_hwrois()

        tab_data = list()
        for (name, values) in hwrois.items():
            tab_data.append([name] + list(values))
        tab_head = ["name", "x0", "y0", "width", "height", "max rate (Hz)"]
        print("\nPossible HWROI values for [{0}]:\n".format(self._model))
        print(tabulate.tabulate(tab_data, tab_head) + "\n")

    def hwroi_set(self, name):
        hwrois = self.__get_hwrois()
        if name not in hwrois:
            raise RuntimeError("Unknown HWROI for model [{0}]".format(self._model))
        roi = hwrois[name]
        print(
            "Setting ROI to ({0},{1},{2},{3}). Max rate will be {4} MHz.".format(*roi)
        )
        self._lima_proxy.image_roi = roi[:4]

    def hwroi_max_rate(self, name):
        hwrois = self.__get_hwrois()
        if name not in hwrois:
            raise RuntimeError("Unknown HWROI for model [{0}]".format(self._model))
        return hwrois[name][4]

    def hwroi_get(self):
        hwrois = self.__get_hwrois()
        img_roi = tuple(self._lima_proxy.image_roi)
        for (name, values) in hwrois.items():
            if img_roi == values[:4]:
                return name
        return "SOFT"

    @property
    def model(self):
        if self._model is None:
            self._model = self.__find_model()
        return self._model

    @LimaProperty
    def synchro_mode(self):
        return "IMAGE"
