# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Base class and enumerations for multichannel analyzers."""

# Imports

import enum
import itertools
import collections
import tabulate

import gevent

from bliss.controllers.mca.roi import RoiConfig
from bliss import global_map
from bliss.common.logtools import *
from bliss.common.utils import autocomplete_property
from bliss.config.beacon_object import BeaconObject

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


# Base class


class BaseMCA(BeaconObject):
    """Generic MCA controller."""

    # Life cycle

    def __init__(self, name, config):
        self._name = name
        BeaconObject.__init__(self, config)
        global_map.register(self, parents_list=["counters", "controllers"])

        self._rois = RoiConfig(self)
        self.init()

    @BeaconObject.lazy_init
    def init(self):
        self.initialize_attributes()
        self.initialize_hardware()

    def initialize_attributes(self):
        raise NotImplementedError

    def initialize_hardware(self):
        raise NotImplementedError

    def finalize(self):
        raise NotImplementedError

    # General properties

    @property
    def name(self):
        return self._name

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

    def info(self):
        info_str = " ---=== MCA ===---\n"
        info_str += f"object: {self.__class__}\n\n"
        info_str += f"Detector brand : {self.detector_brand.name}\n"
        try:
            info_str += f"Detector type  : {self.detector_type.name}\n"
        except:
            info_str += f"Detector type  : UNKNOWN\n"

        # info_str += f"\nConfig:\n"
        # info_str += f"Counters: {self.counters}\n"
        info_str += f"\nROIS:\n"
        info_str += "{0}\n".format(self.rois.__info__())
        info_str += f"\n"

        info_str += f"Acquisition mode : {self.acquisition_mode.name}\n"
        try:
            info_str += f"Spectrum size    : {self.spectrum_size}\n"
        except:
            pass
        try:
            info_str += f"Calib type       : {self.calibration_type}\n"
        except:
            pass
        info_str += f"\n"

        return info_str

    def __info__(self):
        """Standard function called by BLISS Shell typing helper to get info
        about objects.
        """
        try:
            info_str = self.info()
        except Exception:
            log_error(
                self,
                "An error happend during execution of __info__(), use .info() to get it.",
            )

        return info_str

    # Modes

    @property
    def supported_acquisition_modes(self):
        return [AcquisitionMode.MCA]

    @BeaconObject.property(default=AcquisitionMode.MCA)
    def acquisition_mode(self):
        pass

    @acquisition_mode.setter
    def acquisition_mode(self, mode):
        setmode = mode
        if type(mode) == str:
            for acq_mode in self.supported_acquisition_modes:
                if mode.upper() == acq_mode.name:
                    setmode = acq_mode
                    break
        elif type(mode) == int:
            for acq_mode in self.supported_acquisition_modes:
                if mode == acq_mode.value:
                    setmode = acq_mode
        if setmode not in self.supported_acquisition_modes:
            raise ValueError("Not supported acquisition mode [{}]".format(mode))
        return setmode

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
        from bliss.scanning.acquisition.mca import mca_counters

        return mca_counters(self)

    @property
    def counter_groups(self):
        from bliss.scanning.acquisition.mca import mca_counter_groups

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
