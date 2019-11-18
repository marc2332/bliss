# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib
import os

from bliss import global_map
from bliss.common.utils import common_prefix, autocomplete_property
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.config import settings

from bliss.controllers.counter import CounterController, counter_namespace
from bliss.scanning.acquisition.lima import LimaChainNode

from .properties import LimaProperties, LimaProperty
from .bpm import Bpm
from .roi import RoiCounters
from .image import ImageCounter
from .bgsub import BgSub


class CameraBase(object):
    def __init__(self, name, lima_device, proxy):
        pass

    @LimaProperty
    def synchro_mode(self):
        """
        Camera synchronization capability
        Acquisition can either check that the camera is ready for next image with
        **ready_for_next_image** method or waiting to received the image data.

        synchro_mode can be either "TRIGGER" => synchronization with **ready_for_next_image** or
        "IMAGE" => synchronization with **last_image_ready**
        """
        return "TRIGGER"


class ChangeTangoTimeout(object):
    def __init__(self, device, timeout):
        self.__timeout = timeout
        self.__device = device

    def __enter__(self):
        self.__back_timeout = self.__device.get_timeout_millis()
        self.__device.set_timeout_millis(1000 * self.__timeout)

    def __exit__(self, type_, value, traceback):
        self.__device.set_timeout_millis(self.__back_timeout)


class Lima(CounterController):
    """
    Lima controller.
    Basic configuration:
        name: seb_test
        class: Lima
        tango_url: id00/limaccds/simulator1

        directories_mapping:
          default:              # Mapping name
            - path: /data/inhouse
              replace-with: /hz
            - path: /data/visitor
              replace-with: Z:/
          local:
            - path: /data/inhouse
              replace-with: L:/
    """

    _ROI_COUNTERS = "roicounter"
    _BPM = "bpm"
    _BG_SUB = "backgroundsubstraction"

    # Standard interface

    def __init__(self, name, config_tree):
        """Lima controller.

        name -- the controller's name
        config_tree -- controller configuration
        in this dictionary we need to have:
        tango_url -- tango main device url (from class LimaCCDs)
        optional:
        tango_timeout -- tango timeout (s)
        """
        self.__tg_url = config_tree.get("tango_url")
        self.__tg_timeout = config_tree.get("tango_timeout", 3)
        self.__prepare_timeout = config_tree.get("prepare_timeout", None)
        self.__bpm = None
        self.__roi_counters = None
        self.__bg_sub = None
        self._camera = None
        self._image = None
        self._acquisition = None
        self._proxy = self._get_proxy()

        super().__init__(name, chain_node_class=LimaChainNode)

        self._directories_mapping = config_tree.get("directories_mapping", dict())
        self._active_dir_mapping = settings.SimpleSetting(
            "%s:directories_mapping" % name
        )

    @property
    def directories_mapping_names(self):
        return list(self._directories_mapping.keys())

    @property
    def current_directories_mapping(self):
        mapping_name = self._active_dir_mapping.get()
        if mapping_name and mapping_name not in self._directories_mapping:
            self._active_dir_mapping.clear()
            mapping_name = None

        if mapping_name is None:
            # first mapping is selected
            try:
                mapping_name = self.directories_mapping_names[0]
            except IndexError:
                # no mapping
                pass

        return mapping_name

    @property
    def directories_mapping(self):
        mapping_name = self.current_directories_mapping
        return self._directories_mapping.get(mapping_name, [])

    def select_directories_mapping(self, name):
        if name in self._directories_mapping:
            self._active_dir_mapping.set(name)
        else:
            msg = "%s: dir. mapping '%s` does not exist. Should be one of: %s" % (
                self.name,
                name,
                ",".join(self.directories_mapping_names),
            )
            raise ValueError(msg)

    def get_mapped_path(self, path):
        path = os.path.normpath(path)
        for mapping in reversed(self.directories_mapping):
            base_path = mapping["path"]
            replace_with = mapping["replace-with"]
            # os.path.commonprefix function is broken as it returns common
            # characters, that may not form a valid directory path: hence
            # the use of a custom common_prefix function
            if common_prefix([path, base_path]) == base_path:
                return os.path.join(replace_with, os.path.relpath(path, base_path))

        return path

    @property
    def proxy(self):
        return self._proxy

    @autocomplete_property
    def image(self):
        if self._image is None:
            self._image = LimaProperties(
                "LimaImageCounter",
                self.proxy,
                prefix="image_",
                strip_prefix=True,
                base_class=ImageCounter,
                base_class_args=(self, self._proxy),
            )
        return self._image

    @autocomplete_property
    def acquisition(self):
        if self._acquisition is None:
            self._acquisition = LimaProperties(
                "LimaAcquisition", self.proxy, prefix="acq_", strip_prefix=True
            )
        return self._acquisition

    @autocomplete_property
    def roi_counters(self):
        if self.__roi_counters is None:
            roi_counters_proxy = self._get_proxy(self._ROI_COUNTERS)
            self.__roi_counters = RoiCounters(roi_counters_proxy, self)
        return self.__roi_counters

    @autocomplete_property
    def camera(self):
        if self._camera is None:
            camera_type = self._proxy.lima_type
            proxy = self._get_proxy(camera_type)
            camera_type = camera_type.lower()
            try:
                camera_module = importlib.import_module(
                    ".%s" % camera_type, __package__
                )
            except ImportError:
                camera_class = CameraBase
            else:
                camera_class = camera_module.Camera
            self._camera = LimaProperties(
                "LimaCamera",
                proxy,
                base_class=camera_class,
                base_class_args=(self.name, self, proxy),
            )
        return self._camera

    @property
    def camera_type(self):
        return self._proxy.camera_type

    @autocomplete_property
    def bpm(self):
        if self.__bpm is None:
            bpm_proxy = self._get_proxy(Lima._BPM)
            self.__bpm = Bpm(self.name, bpm_proxy, self)
        return self.__bpm

    @property
    def bg_sub(self):
        if self.__bg_sub is None:
            bg_sub_proxy = self._get_proxy(Lima._BG_SUB)
            self.__bg_sub = BgSub(self.name, bg_sub_proxy, self)
        return self.__bg_sub

    @property
    def available_triggers(self):
        """
        This will returns all availables triggers for the camera
        """
        return [v.name for v in self.acquisition.trigger_mode_enum]

    def prepareAcq(self):
        if self.__prepare_timeout is not None:
            with ChangeTangoTimeout(self._proxy, self.__prepare_timeout):
                self._proxy.prepareAcq()
        else:
            self._proxy.prepareAcq()

    def startAcq(self):
        self._proxy.startAcq()

    def stopAcq(self):
        self._proxy.stopAcq()

    def stop_bpm_live(self):
        self._proxy.video_live = False
        self._proxy.stopAcq()
        self.bpm.stop()

    def _get_proxy(self, type_name="LimaCCDs"):
        if type_name == "LimaCCDs":
            device_name = self.__tg_url
        else:
            main_proxy = self.proxy
            device_name = main_proxy.command_inout(
                "getPluginDeviceNameFromType", type_name.lower()
            )
            if not device_name:
                raise RuntimeError(
                    "%s: '%s` proxy cannot be found" % (self.name, type_name)
                )
            if not device_name.startswith("//"):
                # build 'fully qualified domain' name
                # '.get_fqdn()' doesn't work
                db_host = main_proxy.get_db_host()
                db_port = main_proxy.get_db_port()
                device_name = "//%s:%s/%s" % (db_host, db_port, device_name)
        device_proxy = DeviceProxy(device_name)
        device_proxy.set_timeout_millis(1000 * self.__tg_timeout)
        return device_proxy

    def __info__(self):
        attr_list = ("user_detector_name", "camera_model", "camera_type", "lima_type")
        try:
            data = {
                attr.name: ("?" if attr.has_failed else attr.value)
                for attr in self._proxy.read_attributes(attr_list)
            }
        except DevFailed:
            return "Lima {} (Communication error with {!r})".format(
                self.name, self._proxy.dev_name()
            )

        return (
            f"{data['user_detector_name']} - "
            f"{data['camera_model']} ({data['camera_type']}) - Lima {data['lima_type']}\n\n"
            f"Image:\n{self.image.__info__()}\n\n"
            f"Acquisition:\n{self.acquisition.__info__()}\n\n"
            f"ROI Counters:\n{self.roi_counters.__info__()}"
        )

    def __repr__(self):
        attr_list = ("user_detector_name", "lima_type")
        try:
            data = {
                attr.name: ("?" if attr.has_failed else attr.value)
                for attr in self._proxy.read_attributes(attr_list)
            }
            return f"<Lima Controller for {data['user_detector_name']} (Lima {data['lima_type']})>"
        except DevFailed:
            return super().__repr__()

    # Expose counters

    @autocomplete_property
    def counters(self):
        all_counters = [self.image]
        all_counters += list(self.roi_counters.counters)
        try:
            all_counters += list(self.bpm.counters)
        except RuntimeError:
            pass
        return counter_namespace(all_counters)

    @autocomplete_property
    def counter_groups(self):
        dct = {}

        # Image counter
        dct["images"] = counter_namespace([self.image])

        # BPM counters
        try:
            dct["bpm"] = counter_namespace(self.bpm.counters)
        except RuntimeError:
            pass

        # Specific ROI counters
        for counters in self.roi_counters.iter_single_roi_counters():
            dct[counters.name] = counter_namespace(counters)

        # All ROI counters
        dct["roi_counters"] = counter_namespace(self.roi_counters.counters)

        # Default grouped
        default_counters = list(dct["images"]) + list(dct["roi_counters"])
        dct["default"] = counter_namespace(default_counters)

        # Return namespace
        return counter_namespace(dct)
