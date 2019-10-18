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

import gevent

from bliss.controllers.mca.roi import RoiConfig
from bliss import global_map
from bliss.common.logtools import *

# Enums

Brand = enum.Enum(
    "Brand", "XIA OCEAN_OPTICS ISG HAMAMATSU AMPTEK VANTEC CANBERRA RONTEC"
)

DetectorType = enum.Enum(
    "DetectorType",
    "FALCONX XMAP MERCURY MICRO_DXP DXP_2X "
    "MAYA2000 MUSST_MCA MCA8000D DSA1000 MULTIMAX",
)

TriggerMode = enum.Enum("TriggerMode", "SOFTWARE SYNC GATE")

PresetMode = enum.Enum("PresetMode", "NONE REALTIME LIVETIME EVENTS TRIGGERS")

Stats = collections.namedtuple(
    "Stats", "realtime livetime triggers events icr ocr deadtime"
)


# Base class


class BaseMCA(object):
    """Generic MCA controller."""

    # Life cycle

    def __init__(self, name, config):
        self._name = name
        global_map.register(self, parents_list=["counters", "controllers"])
        self._config = config
        self._rois = RoiConfig(self)
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
        info_str += "Detector info:\n"
        info_str += f"brand: {self.detector_brand}\n"
        info_str += f"type: {self.detector_type}\n"
        # info_str += f"detector brand: {self.detector_brand}\n"

        info_str += f"\nConfig:\n"
        # info_str += f"Counters: {self.counters}\n"
        info_str += f"ROIS:\n"
        info_str += f"{self.rois}\n"
        info_str += f"\n"
        try:
            info_str += f"spectrum size: {self.spectrum_size}\n"
        except NotImplementedError:
            pass
        try:
            info_str += f"calib type: {self.calibration_type}\n"
        except NotImplementedError:
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
    def supported_preset_modes(self):
        raise NotImplementedError

    def set_preset_mode(self, mode, *args):
        raise NotImplementedError

    @property
    def supported_trigger_modes(self):
        raise NotImplementedError

    def set_trigger_mode(self, mode):
        raise NotImplementedError

    # Settings

    @property
    def calibration_type(self):
        raise NotImplementedError

    def set_spectrum_range(self, first, last):
        raise NotImplementedError

    @property
    def spectrum_size(self):
        raise NotImplementedError

    def set_spectrum_size(self, size):
        raise NotImplementedError

    # Buffer settings

    @property
    def hardware_points(self):
        raise NotImplementedError

    def set_hardware_points(self, value):
        raise NotImplementedError

    @property
    def block_size(self):
        raise NotImplementedError

    def set_block_size(self, value=None):
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

    @property
    def rois(self):
        return self._rois

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
        self.set_trigger_mode(TriggerMode.SOFTWARE)
        # Preset mode
        self.set_preset_mode(PresetMode.REALTIME, acquisition_time)
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
        self.set_trigger_mode(TriggerMode.GATE)
        # Acquisition number
        self.set_hardware_points(acquisition_number)
        # Block size
        self.set_block_size(block_size)
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
        self.set_trigger_mode(TriggerMode.SYNC)
        # Acquisition number
        self.set_hardware_points(acquisition_number + 1)
        # Block size
        self.set_block_size(block_size)
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
