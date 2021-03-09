# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import requests
import json
import base64
import numpy
import fabio

from bliss.common.logtools import user_print
from .properties import LimaProperty
from .lima_base import CameraBase

DECTRIS_TO_NUMPY = {"<u4": numpy.uint32, "<f4": numpy.float32}


class Camera(CameraBase):
    def __init__(self, name, limadev, proxy):
        super().__init__(name, limadev, proxy)
        self.name = name
        self._device = limadev
        self._proxy = proxy

    @LimaProperty
    def synchro_mode(self):
        return "TRIGGER"

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

    def initialize(self, wait=True):
        self._proxy.initialize()
        if wait:
            self.wait_initialize()

    def wait_initialize(self):
        widx = 0
        while True:
            gevent.sleep(0.5)
            status = self._proxy.plugin_status
            if status in ["READY", "FAULT"]:
                break
            user_print(
                "Detector status: {0:15.15} {1:3.3s}".format(status, "." * (widx % 4)),
                end="\r",
            )
            widx += 1
        user_print(f"Detector status: {status:20.20s}")
        self.wait_high_voltage()

    def delete_memory_files(self):
        self._proxy.deleteMemoryFiles()

    def reset_high_voltage(self, wait=True):
        self._proxy.resetHighVoltage()
        if wait:
            self.wait_high_voltage()

    def wait_high_voltage(self):
        widx = 0
        while True:
            gevent.sleep(0.5)
            state = self._proxy.high_voltage_state
            if state == "READY":
                break
            user_print(
                "High Voltage status: {0:10.10s} {1:3.3s}".format(
                    state, "." * (widx % 4)
                ),
                end="\r",
            )
            widx += 1
        user_print(f"High Voltage status: {state:20.20s}")

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
            "threshold_diff_mode",
            "retrigger",
            "pixel_mask",
            "compression_type",
        ]
        info += self.__get_info_txt("Configuration", config)
        calibration = ["photon_energy", "threshold_energy", "threshold_energy2"]
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

    def __get_request_address(self, subsystem, name):
        dcu = self._proxy.detector_ip
        api = self._proxy.api_version
        return f"http://{dcu}/{subsystem}/api/{api}/{name}"

    def raw_get(self, subsystem, name):
        address = self.__get_request_address(subsystem, name)
        request = requests.get(address)
        if request.status_code != 200:
            raise RuntimeError(
                f"Failed to get {address}\nStatus code = {request.status_code}"
            )
        return request.json()

    def raw_put(self, subsystem, name, dict_data):
        address = self.__get_request_address(subsystem, name)
        data_json = json.dumps(dict_data)
        request = requests.put(address, data=data_json)
        if request.status_code != 200:
            raise RuntimeError(f"Failed to put {address}")
        return request.json()

    def get(self, subsystem, name):
        raw_data = self.raw_get(subsystem, name)
        if type(raw_data["value"]) == dict:
            return self.__raw2numpy(raw_data)
        else:
            return raw_data["value"]

    def __raw2numpy(self, raw_data):
        str_data = base64.standard_b64decode(raw_data["value"]["data"])
        data_type = DECTRIS_TO_NUMPY.get(raw_data["value"]["type"])
        arr_data = numpy.fromstring(str_data, dtype=data_type)
        arr_data.shape = tuple(raw_data["value"]["shape"])
        return arr_data

    def array2edf(self, subsystem, name, filename):
        arr_data = self.get(subsystem, name)
        if type(arr_data) != numpy.ndarray:
            address = self.__get_request_address(subsystem, name)
            raise ValueError(f"{address} does not return an array !!")
        edf_file = fabio.edfimage.EdfImage(arr_data)
        edf_file.save(filename)

    def mask2lima(self, filename):
        arr_data = self.get("detector", "config/pixel_mask")
        lima_data = numpy.array(arr_data == 0, dtype=numpy.uint8)
        edf_file = fabio.edfimage.EdfImage(lima_data)
        edf_file.save(filename)
