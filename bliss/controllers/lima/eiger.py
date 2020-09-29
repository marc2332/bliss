# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from .properties import LimaProperty
from .lima_base import CameraBase


class Camera(CameraBase):
    def __init__(self, name, limadev, proxy):
        super().__init__(name, limadev, proxy)
        self.name = name
        self._device = limadev
        self._proxy = proxy

    @LimaProperty
    def synchro_mode(self):
        return "IMAGE"

    @LimaProperty
    def stream_stats(self):
        stats_val = self._proxy.stream_stats
        stats_txt = "{0:d} frames, {1:.3f} MB, {2:.3f} ms, {3:.3f} GB/s".format(
            int(stats_val[0]),
            stats_val[1] / (1024. * 1024.),
            stats_val[2] / 1.e-3,
            stats_val[3] / (1024. * 1024. * 1024.),
        )
        return stats_txt

    def initialize(self):
        self._proxy.initialize()
        while True:
            gevent.sleep(0.5)
            status = self._proxy.plugin_status
            print(f"Detector status: {status:20.20s}", end="\r")
            if status in ["READY", "FAULT"]:
                break
        print(f"Detector status: {status:20.20s}")

    def delete_memory_files(self):
        self._proxy.deleteMemoryFiles()

    def reset_high_voltage(self):
        self._proxy.resetHighVoltage()

    def __info__(self):
        status = [
            "temperature",
            "humidity",
            "high_voltage_state",
            "plugin_status",
            "cam_status",
            "serie_id",
            "stream_stats",
            "stream_last_info",
        ]
        info = self.__get_info_txt("Detector Status", status)
        config = [
            "countrate_correction",
            "flatfield_correction",
            "auto_summation",
            "efficiency_correction",
            "virtual_pixel_correction",
            "pixel_mask",
            "compression_type",
        ]
        info += self.__get_info_txt("Configuration", config)
        calibration = ["photon_energy", "threshold_energy"]
        info += self.__get_info_txt("Calibration", calibration)
        return info

    def __get_info_txt(self, title, attr_list):
        info = f"{title}:\n"
        hlen = 1 + max([len(attr) for attr in attr_list])
        for name in attr_list:
            try:
                value = getattr(self, name)
            except:
                value = "!ERROR!"
            prop = getattr(self.__class__, name)
            flag = prop.fset and "RW" or "RO"
            info += f"    {name:{hlen}s}: {repr(value)}  [{flag}]\n"
        return info
