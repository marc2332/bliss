# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Base class and enumerations for multichannel analyzers."""

# Imports

import numpy

import enum
import itertools
import collections
import tabulate

import gevent

from bliss.controllers.mca.roi import RoiConfig
from bliss.common.logtools import *
from bliss.common.utils import autocomplete_property
from bliss.config.beacon_object import BeaconObject
from bliss.controllers.counter import CounterController

from bliss.common.counter import Counter
from bliss.controllers.counter import counter_namespace


# Enums

Brand = enum.Enum(
    "Brand", "SIMULATED XIA OCEAN_OPTICS ISG HAMAMATSU AMPTEK VANTEC CANBERRA RONTEC"
)

DetectorType = enum.Enum(
    "DetectorType",
    "SIMULATED FALCONX XMAP MERCURY MICRO_DXP DXP_2X "
    "MAYA2000 MUSST_MCA MCA8000D DSA1000 MULTIMAX",
)

AcquisitionMode = enum.Enum("AcquisitionMode", "MCA HWSCA")

TriggerMode = enum.Enum("TriggerMode", "SOFTWARE SYNC GATE")

PresetMode = enum.Enum("PresetMode", "NONE REALTIME LIVETIME EVENTS TRIGGERS")

Stats = collections.namedtuple(
    "Stats", "realtime livetime triggers events icr ocr deadtime"
)


# MCABeaconObject
class MCABeaconObject(BeaconObject):
    def __init__(self, mca, config):
        self.mca = mca
        super().__init__(config)

    @property
    def name(self):
        return self.mca.name

    @BeaconObject.lazy_init
    def init(self):
        self.mca.initialize_attributes()
        self.mca.initialize_hardware()

    @BeaconObject.property(default=AcquisitionMode.MCA)
    def acquisition_mode(self):
        pass

    @acquisition_mode.setter
    def acquisition_mode(self, mode):
        setmode = mode
        if type(mode) == str:
            for acq_mode in self.mca.supported_acquisition_modes:
                if mode.upper() == acq_mode.name:
                    setmode = acq_mode
                    break
        elif type(mode) == int:
            for acq_mode in self.mca.supported_acquisition_modes:
                if mode == acq_mode.value:
                    setmode = acq_mode
        if setmode not in self.mca.supported_acquisition_modes:
            raise ValueError("Not supported acquisition mode [{}]".format(mode))
        return setmode


# Base class
class BaseMCA(CounterController):
    """Generic MCA controller."""

    # Life cycle

    def __init__(self, name, config, beacon_obj_class=MCABeaconObject):
        CounterController.__init__(self, name)

        self.beacon_obj = beacon_obj_class(self, config)
        self._config = config
        self._rois = RoiConfig(self)
        self.beacon_obj.init()

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):

        from bliss.scanning.acquisition.mca import (
            McaAcquisitionSlave,
            HWScaAcquisitionSlave,
        )

        # --- PARAMETERS WITH DEFAULT VALUE -----------------------------
        acq_mode = self.acquisition_mode
        ### should this move to ctrl_params mechansim?
        if acq_mode == AcquisitionMode.HWSCA:

            params = {
                "npoints": acq_params["npoints"],
                "prepare_once": acq_params["prepare_once"],
                "start_once": acq_params["start_once"],
            }

            return HWScaAcquisitionSlave(self, ctrl_params=ctrl_params, **params)

        elif acq_mode == AcquisitionMode.MCA:
            return McaAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):

        # Return required parameters
        params = {}
        params["npoints"] = acq_params.get("npoints", scan_params.get("npoints", 1))
        params["trigger_mode"] = acq_params.get("trigger_mode", TriggerMode.SOFTWARE)
        params["preset_time"] = acq_params.get(
            "preset_time", scan_params.get("count_time", 1.0)
        )
        params["block_size"] = acq_params.get("block_size", None)
        params["polling_time"] = acq_params.get("polling_time", 0.1)
        params["spectrum_size"] = acq_params.get("spectrum_size", None)
        params["prepare_once"] = acq_params.get("prepare_once", True)
        params["start_once"] = acq_params.get("start_once", True)

        return params

    @property
    def config(self):
        return self.beacon_obj.config

    @property
    def settings(self):
        return self.beacon_obj.settings

    def apply_config(self, reload=False):
        return self.beacon_obj.apply_config(reload=reload)

    def initialize_attributes(self):
        raise NotImplementedError

    def initialize_hardware(self):
        raise NotImplementedError

    def finalize(self):
        raise NotImplementedError

    # Information

    @property
    def detector_brand(self):
        raise NotImplementedError

    @property
    def detector_type(self):
        raise NotImplementedError

    @property
    def elements(self):
        raise NotImplementedError

    def __info__(self):
        """Standard function called by BLISS Shell typing helper to get info
        about objects.
        """

        info_str = "MCA: \n"
        info_str += f"    object: {self.__class__}\n"
        info_str += f"    Detector brand : {self.detector_brand.name}\n"
        try:
            info_str += f"    Detector type  : {self.detector_type.name}\n"
        except Exception:
            info_str += f"    Detector type  : UNKNOWN\n"
        info_str += f"    Acquisition mode : {self.acquisition_mode.name}\n"
        try:
            info_str += f"    Spectrum size    : {self.spectrum_size}\n"
        except Exception:
            pass
        try:
            info_str += f"Calib type       : {self.calibration_type}\n"
        except Exception:
            pass

        # info_str += f"\nConfig:\n"
        # info_str += f"Counters: {self.counters}\n"
        info_str += f"\nROIS:\n"

        info_str_shifted = ""
        for line in self.rois.__info__().split("\n"):
            info_str_shifted += "    " + line + "\n"
        info_str += info_str_shifted
        info_str += f"\n"

        return info_str

    # Modes

    @property
    def supported_acquisition_modes(self):
        return [AcquisitionMode.MCA]

    @property
    def acquisition_mode(self):
        return self.beacon_obj.acquisition_mode

    @acquisition_mode.setter
    def acquisition_mode(self, mode):
        self.beacon_obj.acquisition_mode = mode

    @property
    def supported_preset_modes(self):
        raise NotImplementedError

    @property
    def preset_mode(self):
        raise NotImplementedError

    @preset_mode.setter
    def preset_mode(self, mode):
        raise NotImplementedError

    @property
    def preset_value(self):
        raise NotImplementedError

    @preset_value.setter
    def preset_value(self, value):
        raise NotImplementedError

    @property
    def supported_trigger_modes(self):
        raise NotImplementedError

    @property
    def trigger_mode(self):
        raise NotImplementedError

    @trigger_mode.setter
    def trigger_mode(self, mode):
        raise NotImplementedError

    # Settings

    @property
    def calibration_type(self):
        raise NotImplementedError

    @property
    def spectrum_range(self):
        return (0, self.spectrum_size - 1)

    @spectrum_range.setter
    def spectrum_range(self, first_last_tuple):
        raise NotImplementedError

    @property
    def spectrum_size(self):
        raise NotImplementedError

    @spectrum_size.setter
    def spectrum_size(self, size):
        raise NotImplementedError

    # Buffer settings

    @property
    def hardware_points(self):
        raise NotImplementedError

    @hardware_points.setter
    def hardware_points(self, value):
        raise NotImplementedError

    @property
    def block_size(self):
        raise NotImplementedError

    @block_size.setter
    def block_size(self, value=None):
        raise NotImplementedError

    # Acquisition

    def start_acquisition(self):
        raise NotImplementedError

    def stop_acquisition(self):
        raise NotImplementedError

    def is_acquiring(self):
        raise NotImplementedError

    def get_acquisition_data(self):
        raise NotImplementedError

    def get_acquisition_statistics(self):
        raise NotImplementedError

    def poll_data(self):
        raise NotImplementedError

    # Standard counter access

    @property
    def counters(self):
        return mca_counters(self)

    @property
    def counter_groups(self):
        return mca_counter_groups(self)

    # Roi handling

    @autocomplete_property
    def rois(self):
        return self._rois

    # statistics display

    def statistics(self):
        stats = self.get_acquisition_statistics()
        datas = [
            [idx, val.realtime, val.livetime, val.deadtime, val.icr, val.ocr]
            for (idx, val) in stats.items()
        ]
        heads = ["det#", "RealTime", "LiveTime", "DeadTime", "ICR", "OCR"]
        print("\n" + tabulate.tabulate(datas, heads, numalign="right") + "\n")

    # Extra logic

    def software_controlled_run(self, acquisition_number, polling_time):
        # Loop over acquisitions
        indexes = (
            itertools.count() if acquisition_number == 0 else range(acquisition_number)
        )
        for _ in indexes:
            # Start and wait
            try:
                self.start_acquisition()
                while self.is_acquiring():
                    gevent.sleep(polling_time)
            # Stop in any case
            finally:
                self.stop_acquisition()
            # Send the data
            yield (self.get_acquisition_data(), self.get_acquisition_statistics())

    def hardware_controlled_run(self, acquisition_number, polling_time):
        # Start acquisition
        try:
            self.start_acquisition()
            for point in self.hardware_poll_points(acquisition_number, polling_time):
                yield point
        # Stop in any case
        finally:
            self.stop_acquisition()

    def hardware_poll_points(self, acquisition_number, polling_time):
        assert acquisition_number > 1
        sent = current = 0
        # Loop over polled commands
        while True:
            # Poll data
            done = not self.is_acquiring()
            current, data, statistics = self.poll_data()
            points = list(range(sent, sent + len(data)))
            sent += len(data)
            # Check data integrity
            if sorted(data) != sorted(statistics) != points:
                raise RuntimeError("The polled data overlapped during the acquisition")
            # Send the data
            for n in points:
                yield data[n], statistics[n]
            # Finished
            if sent == current == acquisition_number:
                return
            # Sleep
            if not points and not done:
                gevent.sleep(polling_time)
            # Interrupted
            if done:
                raise RuntimeError(
                    "The device is no longer acquiring "
                    "but {} points are missing.".format(acquisition_number - sent)
                )

    def run_software_acquisition(
        self, acquisition_number, acquisition_time=1., polling_time=0.1
    ):
        log_debug(self, "run_software_acquisition")
        # Trigger mode
        self.trigger_mode = TriggerMode.SOFTWARE
        # Preset mode
        self.preset_mode = PresetMode.REALTIME
        self.preset_value = acquisition_time
        # Run acquisition
        data, statistics = zip(
            *self.software_controlled_run(acquisition_number, polling_time)
        )
        # Return result
        return list(data), list(statistics)

    def run_gate_acquisition(
        self, acquisition_number, block_size=None, polling_time=0.1
    ):
        log_debug(self, "run_gate_acquisition")
        # Trigger mode
        self.trigger_mode = TriggerMode.GATE
        # Acquisition number
        self.hardware_points = acquisition_number
        # Block size
        self.block_size = block_size
        # Run acquisition
        data, statistics = zip(
            *self.hardware_controlled_run(acquisition_number, polling_time)
        )
        # Return result
        return list(data), list(statistics)

    def run_synchronized_acquisition(
        self, acquisition_number, block_size=None, polling_time=0.1
    ):
        log_debug(self, "run_synchronized_acquisition")
        # Trigger mode
        self.trigger_mode = TriggerMode.SYNC
        # Acquisition number
        self.hardware_points = acquisition_number + 1
        # Block size
        self.block_size = block_size
        # Create generator
        data_generator = self.hardware_controlled_run(
            acquisition_number + 1, polling_time
        )
        # Discard first point
        next(data_generator)
        # Get all the points
        data, statistics = zip(*data_generator)
        # Return result
        return list(data), list(statistics)


# Mca counters


class BaseMcaCounter(Counter):
    def __init__(self, mca, base_name, detector=None):
        self.mca = mca
        self.acquisition_device = None
        self.data_points = []
        self.detector_channel = detector
        self.base_name = base_name

        super().__init__(base_name, mca)

    @property
    def name(self):
        if self.detector_channel is None:
            return self.base_name
        return "{}_det{}".format(self.base_name, self.detector_channel)

    # Extra logic
    def register_device(self, device):
        # Current device
        self.data_points = []
        self.acquisition_device = device
        # Consistency checks
        assert self._counter_controller is self.acquisition_device.device
        if self.detector_channel is not None:
            assert self.detector_channel in self._counter_controller.elements

    def extract_point(self, spectrums, stats):
        raise NotImplementedError

    def feed_point(self, spectrums, stats):
        point = self.extract_point(spectrums, stats)
        self.data_points.append(point)
        return point


class StatisticsMcaCounter(BaseMcaCounter):
    def __init__(self, mca, stat_name, detector):
        self.stat_name = stat_name
        assert stat_name in Stats._fields
        super(StatisticsMcaCounter, self).__init__(mca, stat_name, detector)

    @property
    def dtype(self):
        if self.stat_name in ("triggers", "events"):
            return numpy.int
        return numpy.float

    def extract_point(self, spectrums, stats):
        return getattr(stats[self.detector_channel], self.stat_name)


class SpectrumMcaCounter(BaseMcaCounter):
    def __init__(self, mca, detector):
        super(SpectrumMcaCounter, self).__init__(mca, "spectrum", detector)

    @property
    def dtype(self):
        return numpy.uint32

    @property
    def shape(self):
        if self.acquisition_device is None:
            return (self._counter_controller.spectrum_size,)
        return (self.acquisition_device.spectrum_size,)

    def extract_point(self, spectrums, stats):
        return spectrums[self.detector_channel]


class RoiMcaCounter(BaseMcaCounter):
    def __init__(self, mca, roi_name, detector):
        self.roi_name = roi_name
        self.start_index, self.stop_index = None, None
        super(RoiMcaCounter, self).__init__(mca, roi_name, detector)

    def register_device(self, device):
        super(RoiMcaCounter, self).register_device(device)
        self.start_index, self.stop_index = self.mca.rois.get(self.roi_name)

    @property
    def dtype(self):
        return numpy.int

    def compute_roi(self, spectrum):
        return sum(spectrum[self.start_index : self.stop_index])

    def extract_point(self, spectrums, stats):
        return self.compute_roi(spectrums[self.detector_channel])


class RoiSumMcaCounter(RoiMcaCounter):
    def __init__(self, mca, roi_name):
        super(RoiSumMcaCounter, self).__init__(mca, roi_name, None)

    def extract_point(self, spectrums, stats):
        return sum(map(self.compute_roi, spectrums.values()))


class RoiIntegralCounter(BaseMcaCounter):
    def __init__(self, mca, roi_name, detector):
        self.roi_name = roi_name
        self.start_index, self.stop_index = None, None
        super(RoiIntegralCounter, self).__init__(mca, roi_name, detector)

    def register_device(self, device):
        super(RoiIntegralCounter, self).register_device(device)
        self.start_index = 0
        self.stop_index = self.acquisition_device.spectrum_size - 1

    def extract_point(self, spectrums, stats):
        return sum(spectrums[self.detector_channel][:])


def mca_counters(mca):
    """Provide a flat access to all MCA counters.

    - counters.spectrum_det<N>
    - counters.realtime_det<N>
    - counters.livetime_det<N>
    - counters.triggers_det<N>
    - counters.events_det<N>
    - counters.icr_det<N>
    - counters.ocr_det<N>
    - counters.deadtime_det<N>
    """
    # Rois
    counters = [
        RoiMcaCounter(mca, roi, element)
        for element in mca.elements
        for roi in mca.rois.get_names()
    ]
    if mca.acquisition_mode == AcquisitionMode.HWSCA:
        if not len(counters):
            counters += [
                RoiIntegralCounter(mca, "counts", element) for element in mca.elements
            ]
    if mca.acquisition_mode == AcquisitionMode.MCA:
        # Spectrum
        counters += [SpectrumMcaCounter(mca, element) for element in mca.elements]
        # Stats
        counters += [
            StatisticsMcaCounter(mca, stat, element)
            for element in mca.elements
            for stat in Stats._fields
        ]

        # Roi sums
        if len(mca.elements) > 1:
            counters += [RoiSumMcaCounter(mca, roi) for roi in mca.rois.get_names()]

    # Instantiate
    return counter_namespace(counters)


def mca_counter_groups(mca):
    """Provide a group access to MCA counters.

    - groups.spectrum
    - groups.realtime
    - groups.livetime
    - groups.triggers
    - groups.events
    - groups.icr
    - groups.ocr
    - groups.deadtime
    - groups.det<N>
    """
    dct = {}
    counters = mca_counters(mca)
    roi_names = list(mca.rois.get_names())

    # Prefix groups
    prefixes = list(Stats._fields) + ["spectrum"] + roi_names
    for prefix in prefixes:
        dct[prefix] = counter_namespace(
            [counter for counter in counters if counter.name.startswith(prefix)]
        )

    # Suffix groups
    suffixes = ["det{}".format(e) for e in mca.elements]
    for suffix in suffixes:
        dct[suffix] = counter_namespace(
            [counter for counter in counters if counter.name.endswith(suffix)]
        )

    # Instantiate group namespace
    return counter_namespace(dct)
