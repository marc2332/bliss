# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib
import os

from .properties import LimaProperties, LimaProperty
from .bpm import Bpm
from .roi import Roi, RoiCounters
from .image import ImageCounter
from .bgsub import BgSub
from bliss.common.utils import common_prefix
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.common.measurement import namespace, counter_namespace
from bliss.config import settings


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


class Lima(object):
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
    _BPM = "beamviewer"
    _BG_SUB = "backgroundsubstraction"

    # Standard interface

    def create_master_device(self, scan_pars, **settings):
        # Prevent cyclic imports
        from bliss.scanning.acquisition.lima import LimaAcquisitionMaster

        scan_pars.update(settings)

        # Extract information
        npoints = scan_pars.get("npoints", 1)
        acq_expo_time = scan_pars["count_time"]
        save_flag = scan_pars.get("save", False)
        if "INTERNAL_TRIGGER_MULTI" in self.available_triggers:
            default_trigger_mode = "INTERNAL_TRIGGER_MULTI"
        else:
            default_trigger_mode = "INTERNAL_TRIGGER"

        acq_trigger_mode = scan_pars.get("acq_trigger_mode", default_trigger_mode)

        prepare_once = acq_trigger_mode in (
            "INTERNAL_TRIGGER_MULTI",
            "EXTERNAL_GATE",
            "EXTERNAL_TRIGGER_MULTI",
        )
        start_once = acq_trigger_mode not in (
            "INTERNAL_TRIGGER",
            "INTERNAL_TRIGGER_MULTI",
        )
        data_synchronisation = scan_pars.get("data_synchronisation", False)
        if data_synchronisation:
            prepare_once = start_once = False
        acq_nb_frames = npoints if prepare_once else 1
        # Instanciate master
        return LimaAcquisitionMaster(
            self,
            acq_nb_frames=acq_nb_frames,
            acq_expo_time=acq_expo_time,
            acq_trigger_mode=acq_trigger_mode,
            save_flag=save_flag,
            prepare_once=prepare_once,
            start_once=start_once,
        )

    def __init__(self, name, config_tree):
        """Lima controller.

        name -- the controller's name
        config_tree -- controller configuration
        in this dictionary we need to have:
        tango_url -- tango main device url (from class LimaCCDs)
        optional:
        tango_timeout -- tango timeout (s)
        """
        self.name = name
        self.__tg_url = config_tree.get("tango_url")
        self.__tg_timeout = config_tree.get("tango_timeout", 3)
        self.__bpm = None
        self.__roi_counters = None
        self._proxy = self._get_proxy()
        self.__bg_sub = None
        self._camera = None
        self._image = None
        self._acquisition = None
        self._directories_mapping = config_tree.get("directories_mapping", dict())
        self._active_dir_mapping = settings.SimpleSetting(
            "%s:directories_mapping" % name
        )

    @property
    def directories_mapping_names(self):
        return self._directories_mapping.keys()

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

        for mapping in sorted(self.directories_mapping, reverse=True):
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

    @property
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

    @property
    def acquisition(self):
        if self._acquisition is None:
            self._acquisition = LimaProperties(
                "LimaAcquisition", self.proxy, prefix="acq_", strip_prefix=True
            )
        return self._acquisition

    @property
    def roi_counters(self):
        if self.__roi_counters is None:
            roi_counters_proxy = self._get_proxy(self._ROI_COUNTERS)
            self.__roi_counters = RoiCounters(self.name, roi_counters_proxy, self)
        return self.__roi_counters

    @property
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

    @property
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
        self._proxy.prepareAcq()

    def startAcq(self):
        self._proxy.startAcq()

    def stopAcq(self):
        self._proxy.stopAcq()

    def _get_proxy(self, type_name="LimaCCDs"):
        if type_name == "LimaCCDs":
            device_name = self.__tg_url
        else:
            main_proxy = self.proxy
            device_name = main_proxy.command_inout(
                "getPluginDeviceNameFromType", type_name
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

    def __repr__(self):
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
            "{0[user_detector_name]} - "
            "{0[camera_model]} ({0[camera_type]}) - Lima {0[lima_type]}\n\n"
            "Image:\n{1!r}\n\n"
            "Acquisition:\n{2!r}\n\n"
            "ROI Counters:\n{3!r}".format(
                data, self.image, self.acquisition, self.roi_counters
            )
        )

    # Expose counters

    @property
    def counters(self):
        all_counters = [self.image]
        all_counters += list(self.roi_counters.counters)
        try:
            all_counters += list(self.bpm.counters)
        except RuntimeError:
            pass
        return counter_namespace(all_counters)

    @property
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
            dct["roi_counters." + counters.name] = counter_namespace(counters)

        # All ROI counters
        dct["roi_counters"] = counter_namespace(self.roi_counters.counters)

        # Default grouped
        default_counters = list(dct["images"]) + list(dct["roi_counters"])
        dct["default"] = counter_namespace(default_counters)

        # Return namespace
        return namespace(dct)
