# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib
import os
import enum
import numpy as np
from tabulate import tabulate
import textwrap

from bliss import global_map
from bliss.common.utils import common_prefix, autocomplete_property
from bliss.common.tango import DeviceProxy, DevFailed, Database, DevState
from bliss.config import settings
from bliss.config.beacon_object import BeaconObject
from bliss.common.logtools import log_debug

from bliss.controllers.counter import CounterController, counter_namespace
from bliss import current_session

from bliss.config.channels import Cache, clear_cache
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster

from .properties import LimaProperties, LimaProperty
from .bpm import Bpm
from .roi import RoiCounters
from .image import ImageCounter, LimaImageParameters
from .shutter import Shutter

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

    class LimaSavingParameters(BeaconObject):
        _suffix_conversion_dict = {
            "EDFGZ": ".edf.gz",
            "EDFLZ4": ".edf.lz4",
            "HDF5": ".h5",
            "HDF5GZ": ".h5",
            "HDF5BS": ".h5",
            "CBFMHEADER": ".cbf",
        }

        class SavingMode(enum.IntEnum):
            ONE_FILE_PER_FRAME = 0
            ONE_FILE_PER_SCAN = 1
            ONE_FILE_PER_N_FRAMES = 2
            SPECIFY_MAX_FILE_SIZE = 3

        def __init__(self, config, proxy, name):
            self._proxy = proxy
            super().__init__(config, name=name, share_hardware=False, path=["saving"])

        mode = BeaconObject.property_setting(
            "mode", default=SavingMode.ONE_FILE_PER_N_FRAMES
        )

        @mode.setter  ## TODO: write some doc about return of setter
        def mode(self, mode):
            if type(mode) is self.SavingMode:
                return mode
            elif mode in self.SavingMode.__members__.keys():
                return self.SavingMode[mode]
            elif self.SavingMode.__members__.values():
                return self.SavingMode(mode)
            else:
                raise RuntimeError("trying to set unkown saving mode")

        @property
        def available_saving_modes(self):
            return list(self.SavingMode.__members__.keys())

        @property
        def available_saving_formats(self):
            return self._proxy.getAttrStringValueList("saving_format")

        _frames_per_file_doc = """used in ONE_FILE_PER_N_FRAMES mode"""
        frames_per_file = BeaconObject.property_setting(
            "frames_per_file", default=100, doc=_frames_per_file_doc
        )

        _max_file_size_in_MB_doc = """used in N_MB_PER_FILE mode"""
        max_file_size_in_MB = BeaconObject.property_setting(
            "max_file_size_in_MB", default=500, doc=_max_file_size_in_MB_doc
        )

        _max_writing_tasks = BeaconObject.property_setting(
            "_max_writing_tasks", default=1
        )

        @_max_writing_tasks.setter
        def _max_writing_tasks(self, value):
            assert isinstance(value, int)
            assert value > 0
            return value

        _managed_mode = BeaconObject.property_setting(
            "_managed_mode", default="SOFTWARE"
        )

        @_managed_mode.setter
        def _managed_mode(self, value):
            assert isinstance(value, str)
            value = value.upper()
            assert value in ["SOFTWARE", "HARDWARE"]
            return value

        file_format = BeaconObject.property_setting("file_format", default="HDF5")

        @file_format.setter
        def file_format(self, fileformat):
            avail_ff = self.available_saving_formats
            if fileformat in avail_ff:
                return fileformat
            else:
                raise RuntimeError(
                    f"trying to set unkown saving format ({fileformat})."
                    f"available formats are: {avail_ff}"
                )

        def _calc_max_frames_per_file(self):
            (sign, depth, width, height) = self._proxy.image_sizes
            return int(
                round(self.max_file_size_in_MB / (depth * width * height / 1024 ** 2))
            )

        def to_dict(self):
            """
            if saving_frame_per_file = -1 it has to be recalculated in the acq 
            dev and to be replaced by npoints of scan
            """

            if self.mode == self.SavingMode.ONE_FILE_PER_N_FRAMES:
                frames = self.frames_per_file
            elif self.mode == self.SavingMode.ONE_FILE_PER_SCAN:
                frames = -1
            elif self.mode == self.SavingMode.SPECIFY_MAX_FILE_SIZE:
                frames = self._calc_max_frames_per_file()
            else:
                frames = 1

            # force saving_max_writing_task in case any HDF based file format is used
            # this logic could go into lima at some point.
            if "HDF" in self.settings["file_format"]:
                max_tasks = 1
            else:
                max_tasks = self.settings["_max_writing_tasks"]

            return {
                "saving_format": self.settings["file_format"],
                "saving_frame_per_file": frames,
                "saving_suffix": self.suffix_dict[self.settings["file_format"]],
                "saving_max_writing_task": max_tasks,
                "saving_managed_mode": self._managed_mode,
            }

        @property
        def suffix_dict(self):
            _suffix_dict = {k: "." + k.lower() for k in self.available_saving_formats}
            _suffix_dict.update(self._suffix_conversion_dict)
            return _suffix_dict

        def __info__(self):
            tmp = self.to_dict()
            av_modes = "\n                   ".join((self.available_saving_modes))
            return textwrap.dedent(
                f"""                Saving
                --------------
                File Format:  {self.file_format}
                └->  Suffix:  {tmp['saving_suffix']}
                Current Mode: {self.mode.name}
                Available Modes:
                   {av_modes}
                
                for ONE_FILE_PER_N_FRAMES mode
                ------------------------------
                frames_per_file: {self.frames_per_file}
                
                for SPECIFY_MAX_FILE_SIZE mode
                ------------------------------
                max file size (MB):  {self.max_file_size_in_MB}
                └-> frams per file: {self._calc_max_frames_per_file()}
                
                Expert Settings
                ---------------
                config max_writing_tasks:  {self._max_writing_tasks}
                current max_writing_tasks: {tmp['saving_max_writing_task']}
                lima managed_mode:         {self._managed_mode}
                """
            )

    class LimaProcessing(BeaconObject):

        BG_SUB_MODES = {
            "disable": "Disabled",
            "enable_on_fly": "Enabled (Take bg-image on demand)",
            "enable_file": "Enabled (Take bg-image from file)",
        }

        def __init__(self, config, proxy, name):
            self._proxy = proxy
            self._mask_changed = False
            self._flatfield_changed = False
            self._background_changed = False
            super().__init__(
                config, name=name, share_hardware=False, path=["processing"]
            )

        mask = BeaconObject.property_setting("mask", default="")

        @mask.setter
        def mask(self, value):
            assert isinstance(value, str)
            if self.mask != value:
                self._mask_changed = True
            return value

        use_mask = BeaconObject.property_setting("use_mask", default=False)

        @use_mask.setter
        def use_mask(self, value):
            assert isinstance(value, bool)
            return value

        flatfield = BeaconObject.property_setting("flatfield", default="")

        @flatfield.setter
        def flatfield(self, value):
            assert isinstance(value, str)
            if self.flatfield != value:
                self._flatfield_changed = True
            return value

        use_flatfield = BeaconObject.property_setting("use_flatfield", default=False)

        @use_flatfield.setter
        def use_flatfield(self, value):
            assert isinstance(value, bool)
            return value

        runlevel_mask = BeaconObject.property_setting("runlevel_mask", default=0)
        runlevel_flatfield = BeaconObject.property_setting(
            "runlevel_flatfield", default=1
        )
        runlevel_background = BeaconObject.property_setting(
            "runlevel_background", default=2
        )
        runlevel_roicounter = BeaconObject.property_setting(
            "runlevel_roicounter", default=10
        )
        runlevel_bpm = BeaconObject.property_setting("runlevel_bpm", default=10)

        @runlevel_mask.setter
        def runlevel_mask(self, value):
            assert isinstance(value, int)
            return value

        @runlevel_flatfield.setter
        def runlevel_flatfield(self, value):
            assert isinstance(value, int)
            return value

        @runlevel_background.setter
        def runlevel_background(self, value):
            assert isinstance(value, int)
            return value

        @runlevel_roicounter.setter
        def runlevel_roicounter(self, value):
            assert isinstance(value, int)
            return value

        @runlevel_bpm.setter
        def runlevel_bpm(self, value):
            assert isinstance(value, int)
            return value

        background = BeaconObject.property_setting("background", default="")

        @background.setter
        def background(self, value):
            assert isinstance(value, str)
            if self.background != value:
                self._background_changed = True
            return value

        use_background_substraction = BeaconObject.property_setting(
            "use_background_substraction", default="disable"
        )

        @use_background_substraction.setter
        def use_background_substraction(self, value):
            assert isinstance(value, str)
            assert value in self.BG_SUB_MODES.keys()
            return value

        def to_dict(self):
            return {
                "use_mask": self.use_mask,
                "use_flatfield": self.use_flatfield,
                "use_background_substraction": self.use_background_substraction,
            }

        def __info__(self):
            return textwrap.dedent(
                f"""            Mask
            ----
            use mask: {self.use_mask}
            mask image path: {self.mask}
            
            Flatfield
            ---------
            use flatfield: {self.use_flatfield}
            flatfield image path: {self.flatfield} 
            
            Background Substraction
            -----------------------
            mode: {self.BG_SUB_MODES[self.use_background_substraction]}
            background_image_path: {self.background}
            
            Expert Settings
            ---------------
            Lima Run-Level:
               Mask           {self.runlevel_mask}
               Flatfield:     {self.runlevel_flatfield}
               Bg-Sub:        {self.runlevel_background}
               Roi Counters:  {self.runlevel_roicounter}
               BPM:           {self.runlevel_bpm}
            """
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
        self.__tg_url = config_tree.get("tango_url")
        self.__tg_timeout = config_tree.get("tango_timeout", 3)
        self.__prepare_timeout = config_tree.get("prepare_timeout", None)
        self.__bpm = None
        self.__roi_counters = None
        self._instrument_name = config_tree._config.root.get("instrument", "")
        self.__bg_sub = None
        self.__last = None
        self._camera = None
        self._image = None
        self._shutter = None
        self._acquisition = None
        self._accumulation = None
        self._proxy = self._get_proxy()
        self._cached_ctrl_params = {}

        super().__init__(name)

        self._directories_mapping = config_tree.get("directories_mapping", dict())
        self._active_dir_mapping = settings.SimpleSetting(
            "%s:directories_mapping" % name
        )

        global_map.register("lima", ["global"])
        global_map.register(self, parents_list=["lima", "controllers"])

        clear_cache(self)

        if current_session:
            name_prefix = current_session.name
        else:
            name_prefix = ""

        self._saving = self.LimaSavingParameters(
            config_tree, self._proxy, f"{name_prefix}:{self.name}:saving"
        )

        self._processing = self.LimaProcessing(
            config_tree, self._proxy, f"{name_prefix}:{self.name}:processing"
        )

        self._image_params = LimaImageParameters(
            config_tree, self._proxy, f"{name_prefix}:{self.name}:image"
        )

        self.set_bliss_device_name()

    def set_bliss_device_name(self):
        ### use tango db to check if device is exported
        ### if yes, set user device name on init.
        if hasattr(self.proxy, "lima_version"):
            try:
                if Database().get_device_info(self.__tg_url).exported:
                    try:
                        self.proxy.user_instrument_name = self._instrument_name
                    except DevFailed:
                        pass
                    try:
                        self.proxy.user_detector_name = self.name
                    except DevFailed:
                        pass
            except (RuntimeError, DevFailed):
                pass

    def __close__(self):
        self._processing.__close__()
        self._saving.__close__()
        self._image_params.__close__()

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return LimaAcquisitionMaster(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):

        npoints = acq_params.get("acq_nb_frames", scan_params.get("npoints", 1))

        try:
            acq_expo_time = acq_params["acq_expo_time"]
        except KeyError:
            acq_expo_time = scan_params["count_time"]

        if "INTERNAL_TRIGGER_MULTI" in self.available_triggers:
            default_trigger_mode = "INTERNAL_TRIGGER_MULTI"
        else:
            default_trigger_mode = "INTERNAL_TRIGGER"

        acq_trigger_mode = acq_params.get("acq_trigger_mode", default_trigger_mode)

        prepare_once = acq_trigger_mode in (
            "INTERNAL_TRIGGER_MULTI",
            "EXTERNAL_GATE",
            "EXTERNAL_TRIGGER_MULTI",
        )
        start_once = acq_trigger_mode not in (
            "INTERNAL_TRIGGER",
            "INTERNAL_TRIGGER_MULTI",
        )

        data_synchronisation = scan_params.get("data_synchronisation", False)
        if data_synchronisation:
            prepare_once = start_once = False

        acq_nb_frames = npoints if prepare_once else 1

        stat_history = npoints

        # Return required parameters
        params = {}
        params["acq_nb_frames"] = acq_nb_frames
        params["acq_expo_time"] = acq_expo_time
        params["acq_trigger_mode"] = acq_trigger_mode
        params["acq_mode"] = acq_params.get("acq_mode", "SINGLE")
        params["wait_frame_id"] = range(acq_nb_frames)
        params["prepare_once"] = prepare_once
        params["start_once"] = start_once
        params["stat_history"] = stat_history

        return params

    @property
    def _lima_hash(self):
        """
        returns a string that is used to describe the tango device state
        """
        return f"{self._proxy.image_sizes}{self._proxy.image_roi}{self._proxy.image_flip}{self._proxy.image_bin}{self._proxy.image_rotation}"

    def apply_parameters(self, ctrl_params):

        if "image_roi" in ctrl_params:
            # make sure that image_roi is applied last (last element in ctrl_params)
            ctrl_params["image_roi"] = ctrl_params.pop("image_roi")

        def needs_update(key, value):
            if key not in self._cached_ctrl_params:
                self._cached_ctrl_params[key] = Cache(self, key)
            if str(self._cached_ctrl_params[key].value) != str(value):
                self._cached_ctrl_params[key].value = value
                return True
            else:
                return False

        self.set_bliss_device_name()

        server_start_timestamp = needs_update(
            "server_start_timestamp",
            Database().get_device_info(self.__tg_url).started_date,
        )
        last_session_used = needs_update("last_session_used", str(current_session.name))
        lima_hash_different = Cache(self, "lima_hash").value != self._lima_hash

        update_all = server_start_timestamp or last_session_used or lima_hash_different
        if update_all:
            log_debug(self, "All parameters will be refeshed on %s", self.name)

        assert ctrl_params["saving_format"] in self.saving.available_saving_formats
        ctrl_params["saving_suffix"] = self.saving.suffix_dict[
            ctrl_params["saving_format"]
        ]

        use_mask = ctrl_params.pop("use_mask")
        assert type(use_mask) == bool
        if (
            needs_update("use_mask", use_mask)
            or self.processing._mask_changed
            or update_all
        ):
            maskp = self._get_proxy("mask")
            maskp.Stop()
            if use_mask:
                log_debug(self, " uploading new mask on %s", self.name)
                maskp.setMaskImage(self.processing.mask)
                self.processing._mask_changed = False
                maskp.RunLevel = self.processing.runlevel_mask
                maskp.Start()
                maskp.type = "STANDARD"

        use_flatfield = ctrl_params.pop("use_flatfield")
        assert type(use_flatfield) == bool
        if (
            needs_update("use_flatfield", use_flatfield)
            or self.processing._flatfield_changed
            or update_all
        ):
            ff_proxy = self._get_proxy("flatfield")
            ff_proxy.Stop()
            if use_flatfield:
                log_debug(self, " uploading flatfield on %s", self.name)
                ff_proxy.setFlatFieldImage(self.processing.flatfield)
                ff_proxy.RunLevel = self.processing.runlevel_flatfield
                ff_proxy.normalize = 0
                self.processing._flatfield_changed = False
                ff_proxy.Start()

        use_bg_sub = ctrl_params.pop("use_background_substraction")
        assert isinstance(use_bg_sub, str)
        assert use_bg_sub in self.processing.BG_SUB_MODES.keys()
        if (
            needs_update("use_background_substraction", use_bg_sub)
            or self.processing._background_changed
            or update_all
        ):
            bg_proxy = self._get_proxy("backgroundsubstraction")
            log_debug(
                self,
                " stopping background sub proxy on %s and setting runlevel to %s",
                self.name,
                self.processing.runlevel_background,
            )
            bg_proxy.Stop()
            bg_proxy.RunLevel = self.processing.runlevel_background
            if use_bg_sub == "enable_on_fly":
                log_debug(self, " starting background sub proxy of %s", self.name)
                bg_proxy.Start()
            elif use_bg_sub == "enable_file":
                log_debug(self, " uploading background on %s", self.name)
                bg_proxy.setbackgroundimage(self.processing.background)
                log_debug(self, " starting background sub proxy of %s", self.name)
                bg_proxy.Start()

        if (
            needs_update("runlevel_roicounter", self.processing.runlevel_roicounter)
            or update_all
        ):
            proxy = self.roi_counters._proxy
            state = proxy.State()
            if state == DevState.ON:
                log_debug(
                    self, "stop, runlevel, start on roi_counter proxy of %s", self.name
                )
                proxy.Stop()
                proxy.RunLevel = self.processing.runlevel_roicounter
                proxy.Start()
            else:
                log_debug(self, "set runlevel on roi_counter proxy of %s", self.name)
                proxy.RunLevel = self.processing.runlevel_roicounter

        if needs_update("runlevel_bpm", self.processing.runlevel_bpm) or update_all:
            proxy = self.bpm._proxy
            state = proxy.State()
            if state == DevState.ON:
                log_debug(self, "stop, runlevel, start on bpm proxy of %s", self.name)
                proxy.Stop()
                proxy.RunLevel = self.processing.runlevel_bpm
                proxy.Start()
            else:
                log_debug(self, "set runlevel on bpm proxy of %s", self.name)
                proxy.RunLevel = self.processing.runlevel_bpm

        for key, value in ctrl_params.items():
            if needs_update(key, value) or update_all:
                log_debug(self, "updating %s on %s to %s", key, self.name, value)
                setattr(self.proxy, key, value)

        # update lima_hash with last set of parameters
        Cache(self, "lima_hash").value = self._lima_hash

    def get_current_parameters(self):
        return {
            **self.saving.to_dict(),
            **self.processing.to_dict(),
            **self._image_params.to_dict(),
        }

    def clear_cache(self):
        clear_cache(self)

    @autocomplete_property
    def processing(self):
        return self._processing

    def configure_saving(self):
        """shell dialog for saving related settings"""
        from bliss.shell.dialog.controller.lima_dialogs import (
            lima_saving_parameters_dialog
        )

        lima_saving_parameters_dialog(self)

    def configure_processing(self):
        """shell dialog for processing related settings"""
        from bliss.shell.dialog.controller.lima_dialogs import lima_processing_dialog

        lima_processing_dialog(self)

    def configure_image(self):
        """shell dialog for image related settings"""
        from bliss.shell.dialog.controller.lima_dialogs import lima_image_dialog

        lima_image_dialog(self)

    @autocomplete_property
    def saving(self):
        return self._saving

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

    @autocomplete_property
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
    def shutter(self):
        if self._shutter is None:
            self._shutter = LimaProperties(
                "LimaShutter",
                self.proxy,
                prefix="shutter_",
                strip_prefix=True,
                base_class=Shutter,
                base_class_args=(self, self._proxy),
            )
        return self._shutter

    @autocomplete_property
    def last(self):
        if self.__last is None:
            self.__last = LimaProperties(
                "LimaImageStatus", self.proxy, prefix="last_", strip_prefix=True
            )
        return self.__last

    @autocomplete_property
    def acquisition(self):
        if self._acquisition is None:
            self._acquisition = LimaProperties(
                "LimaAcquisition", self.proxy, prefix="acq_", strip_prefix=True
            )
        return self._acquisition

    @autocomplete_property
    def accumulation(self):
        if self._accumulation is None:
            self._accumulation = LimaProperties(
                "LimaAccumulation", self.proxy, prefix="acc_", strip_prefix=True
            )
        return self._accumulation

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

    @autocomplete_property
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

        info_str = (
            f"{data['user_detector_name']} - "
            f"{data['camera_model']} ({data['camera_type']}) - Lima {data['lima_type']}\n\n"
            f"Image:\n{self.image.__info__()}\n\n"
            f"Acquisition:\n{self.acquisition.__info__()}\n\n"
            f"{self.roi_counters.__info__()}\n\n"
            f"{self.bpm.__info__()}\n\n"
            f"{self.saving.__info__()}\n\n"
            f"{self.processing.__info__()}\n"
        )

        return info_str

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
