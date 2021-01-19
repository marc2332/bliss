# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib
import numpy
import os

from bliss import global_map
from bliss.common.utils import common_prefix, autocomplete_property
from bliss.common.tango import DeviceProxy, DevFailed, Database, DevState
from bliss.config import settings
from bliss.config.beacon_object import BeaconObject
from bliss.common.logtools import log_debug

from bliss.controllers.counter import CounterController, counter_namespace
from bliss import current_session

from bliss.config.channels import Cache, clear_cache

from bliss.controllers.lima.properties import (
    LimaProperties,
    LimaProperty,
    LimaAttrGetterSetter,
)
from bliss.controllers.lima.bpm import Bpm
from bliss.controllers.lima.roi import (
    RoiCounters,
    RoiProfileController,
    RoiCollectionController,
)
from bliss.controllers.lima.image import ImageCounter
from bliss.controllers.lima.shutter import Shutter
from bliss.controllers.lima.bgsub import BgSub
from bliss.controllers.lima.debug import LimaDebug
from bliss.controllers.lima.saving import LimaSavingParameters
from bliss.controllers.lima.processing import LimaProcessing


class LimaBeaconObject(BeaconObject):
    @BeaconObject.lazy_init
    def to_dict(self):
        # inherits from 'prefix' from LimaAttrGetterSetter
        return {self.prefix + k: v for k, v in self.settings.items()}

    def __info__(self):
        return LimaAttrGetterSetter.__info__(self)


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
    _ROI_PROFILES = "roi2spectrum"
    _ROI_COLLECTION = "roicollection"
    _BPM = "bpm"
    _BG_SUB = "backgroundsubstraction"
    # backward compatibility for old pickled objects in redis,
    # since classes definition moved
    LimaSavingParameters = LimaSavingParameters
    LimaProcessing = LimaProcessing

    def __init__(self, name, config_node):
        """Lima controller.

        name -- the controller's name
        config_node -- controller configuration
        in this dictionary we need to have:
        tango_url -- tango main device url (from class LimaCCDs)
        optional:
        tango_timeout -- tango timeout (s)
        """
        self.__tg_url = config_node.get("tango_url")
        self.__tg_timeout = config_node.get("tango_timeout", 3)
        self.__prepare_timeout = config_node.get("prepare_timeout", None)
        self.__bpm = None
        self.__roi_counters = None
        self.__roi_profiles = None
        self.__roi_collection = None
        self._instrument_name = config_node.root.get("instrument", "")
        self.__bg_sub = None
        self.__last = None
        self._config_node = config_node
        self._camera = None
        self._disable_bpm = config_node.get("disable_bpm", False)
        self._image = None
        self._shutter = None
        self._acquisition = None
        self._accumulation = None
        self._saving = None
        self._processing = None
        self.__image_params = None
        self._debug = None
        self._proxy = self._get_proxy()
        self._cached_ctrl_params = {}

        super().__init__(name)

        self._directories_mapping = config_node.get("directories_mapping", dict())
        self._active_dir_mapping = settings.SimpleSetting(
            "%s:directories_mapping" % name
        )

        global_map.register("lima", parents_list=["global"])
        global_map.register(
            self, parents_list=["lima", "controllers"], children_list=[self._proxy]
        )

    @property
    def disable_bpm(self):
        return self._disable_bpm

    def set_bliss_device_name(self):
        if hasattr(self.proxy, "lima_version"):
            try:
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

    @property
    def _name_prefix(self):
        try:
            return f"{current_session.name}:{self.name}"
        except AttributeError:
            return self.name

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # avoid cyclic import
        from bliss.scanning.acquisition.lima import LimaAcquisitionMaster

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

        # Internal_trigger: the software trigger, start the acquisition immediately after acqStart()
        #  all the acq_nb_frames are acquired in an sequence.

        # Internal_trigger_multi: like internal_trigger except that for each frame startAcq() has to be called.

        # External_trigger: wait for an external trigger signal to start the acquisition of acq_nb_frames.

        # External_trigger_multi: like External_trigger except that each frames need a
        # new trigger (e.g. 4 pulses for 4 frames)

        # External_gate: wait for a gate signal for each frame, the gate period is the exposure time.

        # External_start_stop

        prepare_once = acq_trigger_mode in (
            "INTERNAL_TRIGGER_MULTI",
            "EXTERNAL_GATE",
            "EXTERNAL_TRIGGER_MULTI",
            "EXTERNAL_START_STOP",
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

    def _needs_update(self, key, new_value, proxy=None):
        try:
            cached_value = self._cached_ctrl_params[key].value
        except KeyError:
            self._cached_ctrl_params[key] = Cache(self, key)
            self._cached_ctrl_params[key].value = str(new_value)
            if proxy:
                # check if new value is different from Lima value
                try:
                    lima_value = getattr(proxy, key)
                except AttributeError:
                    return True
                if isinstance(lima_value, numpy.ndarray):
                    return str(lima_value) != str(new_value)
                try:
                    return lima_value != new_value
                except ValueError:
                    return str(lima_value) != str(new_value)
            return True
        else:
            if cached_value != str(new_value):
                self._cached_ctrl_params[key].value = str(new_value)
                return True
        return False

    def apply_parameters(self, ctrl_params):

        self.set_bliss_device_name()

        # -----------------------------------------------------------------------------------

        server_started_date = Database().get_device_info(self.__tg_url).started_date
        server_start_timestamp_cache = Cache(self, "server_start_timestamp")
        server_restarted = server_start_timestamp_cache.value != server_started_date
        if server_restarted:
            server_start_timestamp_cache.value = server_started_date
        last_session_cache = Cache(self, "last_session")
        other_session_started = last_session_cache.value != current_session.name
        if other_session_started:
            last_session_cache.value = current_session.name
        lima_hash_different = Cache(self, "lima_hash").value != self._lima_hash

        update_all = server_restarted or other_session_started or lima_hash_different
        if update_all:
            log_debug(self, "All parameters will be refeshed on %s", self.name)
            self._cached_ctrl_params.clear()

        assert ctrl_params["saving_format"] in self.saving.available_saving_formats
        ctrl_params["saving_suffix"] = self.saving.suffix_dict[
            ctrl_params["saving_format"]
        ]

        use_mask = ctrl_params.pop("use_mask")
        assert type(use_mask) == bool
        if self.processing._mask_changed or self._needs_update("use_mask", use_mask):
            maskp = self._get_proxy("mask")
            global_map.register(maskp, parents_list=[self], tag="mask")
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
        if self.processing._flatfield_changed or self._needs_update(
            "use_flatfield", use_flatfield
        ):
            ff_proxy = self._get_proxy("flatfield")
            global_map.register(ff_proxy, parents_list=[self], tag="flatfield")
            ff_proxy.Stop()
            if use_flatfield:
                log_debug(self, " uploading flatfield on %s", self.name)
                ff_proxy.setFlatFieldImage(self.processing.flatfield)
                ff_proxy.RunLevel = self.processing.runlevel_flatfield
                ff_proxy.normalize = 0
                self.processing._flatfield_changed = False
                ff_proxy.Start()

        use_bg_sub = ctrl_params.pop("use_background")
        assert type(use_bg_sub) == bool
        # assert use_bg_sub in self.processing.BG_SUB_MODES.keys()
        if self.processing._background_changed or self._needs_update(
            "use_background", use_bg_sub
        ):
            bg_proxy = self._get_proxy("backgroundsubstraction")
            global_map.register(bg_proxy, parents_list=[self], tag="bg_sub")
            log_debug(
                self,
                " stopping background sub proxy on %s and setting runlevel to %s",
                self.name,
                self.processing.runlevel_background,
            )
            bg_proxy.Stop()
            bg_proxy.RunLevel = self.processing.runlevel_background
            if use_bg_sub:
                if self.processing.background_source == "file":
                    log_debug(self, " uploading background on %s", self.name)
                    log_debug(self, " background file = %s", self.processing.background)
                    bg_proxy.setbackgroundimage(self.processing.background)
                log_debug(self, " starting background sub proxy of %s", self.name)
                bg_proxy.Start()

        if self._needs_update(
            "runlevel_roicounter",
            self.processing.runlevel_roicounter,
            proxy=self.roi_counters._proxy,
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

        if (
            self.roi_collection is not None
        ):  # CHECK IF LIMA SERVER COLLECTION PLUGIN IS AVAILABLE (see lima server version)
            if self._needs_update(
                "runlevel_roicollection",
                self.processing.runlevel_roicollection,
                proxy=self.roi_collection._proxy,
            ):
                proxy = self.roi_collection._proxy
                state = proxy.State()
                if state == DevState.ON:
                    log_debug(
                        self,
                        "stop, runlevel, start on roi_collection proxy of %s",
                        self.name,
                    )
                    proxy.Stop()
                    proxy.RunLevel = self.processing.runlevel_roicollection
                    proxy.Start()
                else:
                    log_debug(
                        self, "set runlevel on roi_collection proxy of %s", self.name
                    )
                    proxy.RunLevel = self.processing.runlevel_roicollection

        if self._needs_update(
            "runlevel_roiprofiles",
            self.processing.runlevel_roiprofiles,
            proxy=self.roi_profiles._proxy,
        ):
            proxy = self.roi_profiles._proxy
            state = proxy.State()
            if state == DevState.ON:
                log_debug(
                    self, "stop, runlevel, start on roi_profiles proxy of %s", self.name
                )
                proxy.Stop()
                proxy.RunLevel = self.processing.runlevel_roiprofiles
                proxy.Start()
            else:
                log_debug(self, "set runlevel on roi_profiles proxy of %s", self.name)
                proxy.RunLevel = self.processing.runlevel_roiprofiles

        if self._needs_update(
            "runlevel_bpm", self.processing.runlevel_bpm, proxy=self.bpm._proxy
        ):
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

        # ------- send the params to tango-lima ---------------------------------------------

        # Lima rules and order of image transformations:
        # 0) set back binning to 1,1 before any flip or rot modif (else lima crashes if a roi/subarea is already defined with lima-core < 1.9.6rc3))
        # 1) flip [Left-Right, Up-Down]  (in bin 1,1 only else lima crashes if a roi/subarea is already defined)
        # 2) rotation (clockwise and negative angles not possible) (in bin 1,1 only for same reason)
        # 3) binning
        # 4) roi (expressed in the current state f(flip, rot, bin))

        # --- Extract special params from ctrl_params and sort them -----------
        special_params = {}

        if "image_bin" in ctrl_params:
            special_params["image_bin"] = numpy.array(ctrl_params.pop("image_bin"))

        if "image_flip" in ctrl_params:
            special_params["image_flip"] = numpy.array(ctrl_params.pop("image_flip"))

        if "image_rotation" in ctrl_params:
            special_params["image_rotation"] = ctrl_params.pop("image_rotation")

        if "image_roi" in ctrl_params:
            # make sure that image_roi is applied last
            special_params["image_roi"] = numpy.array(ctrl_params.pop("image_roi"))

        # --- Apply standard params (special_params excluded/removed)
        for key, value in ctrl_params.items():
            if self._needs_update(key, value, self.proxy):
                log_debug(self, "apply parameter %s on %s to %s", key, self.name, value)
                setattr(self.proxy, key, value)

        # --- Select special params that must be updated (caching/filtering)
        _tmp = {}
        for key, value in special_params.items():
            if self._needs_update(key, value, self.proxy):
                _tmp[key] = value
        special_params = _tmp

        # be sure to apply the roi as last operation
        if "image_roi" in special_params:
            special_params["image_roi"] = special_params.pop("image_roi")

        # --- Apply special params -----------------------

        for key, value in special_params.items():
            log_debug(self, "apply parameter %s on %s to %s", key, self.name, value)
            setattr(self.proxy, key, value)

        # update lima_hash with last set of parameters
        Cache(self, "lima_hash").value = self._lima_hash

    def get_current_parameters(self):
        return {
            **self.saving.to_dict(),
            **self.processing.to_dict(),
            **self.image.to_dict(),
            **self.accumulation.to_dict(),
        }

    def clear_cache(self):
        clear_cache(self)

    @autocomplete_property
    def debug(self):
        if self._debug is None:
            self._debug = LimaDebug(self.name, self._proxy)
        return self._debug

    @autocomplete_property
    def processing(self):
        if self._processing is None:
            self._processing = LimaProcessing(
                self._config_node, self._proxy, f"{self._name_prefix}:processing"
            )
        return self._processing

    @autocomplete_property
    def saving(self):
        if self._saving is None:
            self._saving = LimaSavingParameters(
                self._config_node, self._proxy, f"{self._name_prefix}:saving"
            )
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
            self._image = ImageCounter(self)
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
                "LimaAccumulation",
                self.proxy,
                prefix="acc_",
                strip_prefix=True,
                base_class=LimaBeaconObject,
                base_class_args=(self._config_node,),
                base_class_kwargs={
                    "name": f"{self._name_prefix}:accumulation",
                    "share_hardware": False,
                    "path": ["accumulation"],
                },
            )
        return self._accumulation

    @autocomplete_property
    def roi_counters(self):
        if self.__roi_counters is None:
            roi_counters_proxy = self._get_proxy(self._ROI_COUNTERS)
            self.__roi_counters = RoiCounters(roi_counters_proxy, self)
            global_map.register(
                self.__roi_counters,
                parents_list=[self],
                children_list=[roi_counters_proxy],
            )
        return self.__roi_counters

    @autocomplete_property
    def roi_collection(self):
        if self.__roi_collection is None:
            try:
                roi_collection_proxy = self._get_proxy(self._ROI_COLLECTION)
            except RuntimeError:
                # Lima server doesnt have the roi_collection plugin installed/activated
                return

            else:
                self.__roi_collection = RoiCollectionController(
                    roi_collection_proxy, self
                )
                global_map.register(
                    self.__roi_collection,
                    parents_list=[self],
                    children_list=[roi_collection_proxy],
                )
        return self.__roi_collection

    @autocomplete_property
    def roi_profiles(self):
        if self.__roi_profiles is None:
            roi_profiles_proxy = self._get_proxy(self._ROI_PROFILES)
            self.__roi_profiles = RoiProfileController(roi_profiles_proxy, self)
            global_map.register(
                self.__roi_profiles,
                parents_list=[self],
                children_list=[roi_profiles_proxy],
            )
        return self.__roi_profiles

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
            global_map.register(
                self._camera, parents_list=[self], children_list=[proxy]
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
            global_map.register(
                self.__bpm, parents_list=[self], children_list=[bpm_proxy]
            )

        return self.__bpm

    @autocomplete_property
    def bg_sub(self):
        if self.__bg_sub is None:
            bg_sub_proxy = self._get_proxy(Lima._BG_SUB)
            self.__bg_sub = BgSub(self.name, bg_sub_proxy, self)
            global_map.register(
                self.__bg_sub, parents_list=[self], children_list=[bg_sub_proxy]
            )
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
            f"{self.roi_profiles.__info__()}\n\n"
            f"{self.roi_collection.__info__() if self.roi_collection is not None else 'Roi Collection: server plugin not found!'}\n\n"
            f"{self.bpm.__info__()}\n\n"
            f"{self.saving.__info__()}\n\n"
            f"{self.processing.__info__()}\n"
        )

        return info_str

    # Expose counters

    @autocomplete_property
    def counters(self):
        counter_groups = self.counter_groups
        counters = list(self.counter_groups.images)
        if not self.disable_bpm:
            counters += list(self.counter_groups.bpm)
        counters += list(self.counter_groups.roi_counters)
        counters += list(self.counter_groups.roi_profiles)
        if (
            self.roi_collection is not None
        ):  # CHECK IF LIMA SERVER COLLECTION PLUGIN IS AVAILABLE (see lima server version)
            counters += list(self.counter_groups.roi_collection)
        return counter_namespace(counters)

    @autocomplete_property
    def counter_groups(self):
        dct = {}

        # Image counter
        try:
            dct["images"] = counter_namespace([self.image])
        except (RuntimeError, DevFailed):
            dct["images"] = counter_namespace([])

        # BPM counters
        if not self.disable_bpm:
            try:
                dct["bpm"] = counter_namespace(self.bpm.counters)
            except (RuntimeError, DevFailed):
                dct["bpm"] = counter_namespace([])

        # All ROI counters ( => cnt = cam.counter_groups['roi_counters']['r1_sum'], i.e all counters of all rois)
        try:
            dct["roi_counters"] = counter_namespace(self.roi_counters.counters)
        except (RuntimeError, DevFailed):
            dct["roi_counters"] = counter_namespace([])
        else:
            # Specific ROI counters  ( => cnt = cam.counter_groups['r1']['r1_sum'], i.e counters per roi)
            for single_roi_counters in self.roi_counters.iter_single_roi_counters():
                dct[single_roi_counters.name] = counter_namespace(single_roi_counters)

        # All roi_profiles counters
        try:
            dct["roi_profiles"] = counter_namespace(self.roi_profiles.counters)
        except (RuntimeError, DevFailed):
            dct["roi_profiles"] = counter_namespace([])
        else:
            # Specific roi_profiles counters
            for counter in self.roi_profiles.counters:
                dct[
                    counter.name
                ] = (
                    counter
                )  # ??? or (for symmetry) counter_namespace([counter]) => cnt = cam.counter_groups['s2']['s2'] ???

        # All roi_collection counters
        if self.roi_collection is not None:
            try:
                dct["roi_collection"] = counter_namespace(self.roi_collection.counters)
            except (RuntimeError, DevFailed):
                dct["roi_collection"] = counter_namespace([])
            else:
                # Specific roi_collection counters
                for counter in self.roi_collection.counters:
                    dct[counter.name] = counter  # ???

        # Default grouped
        default_counters = (
            list(dct["images"])
            + list(dct["roi_counters"])
            + list(dct["roi_profiles"])
            # + list(dct["roi_collection"])
        )

        if self.roi_collection is not None:
            default_counters += list(dct["roi_collection"])

        dct["default"] = counter_namespace(default_counters)

        # Return namespace
        return counter_namespace(dct)
