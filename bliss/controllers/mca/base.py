# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Base class and enumerations for multichannel analyzers."""

# Imports

import enum
import warnings
import collections

import gevent


# Enums

Brand = enum.Enum(
    'Brand',
    'XIA OCEAN_OPTICS ISG HAMAMATSU AMPTEK VANTEC CANBERRA RONTEC')

DetectorType = enum.Enum(
    'DetectorType',
    'FALCONX XMAP MERCURY MICRO_DXP DXP_2X '
    'MAYA2000 MUSST_MCA MCA8000D DSA1000 MULTIMAX')

TriggerMode = enum.Enum(
    'TriggerMode',
    'SOFTWARE SYNC GATE')

PresetMode = enum.Enum(
    'PresetMode',
    'NONE REALTIME LIVETIME EVENTS TRIGGERS')

Stats = collections.namedtuple(
    'Stats',
    'realtime livetime triggers events icr ocr deadtime')


# Base class

class BaseMCA(object):
    """Generic MCA controller."""

    # Life cycle

    def __init__(self, name, config):
        self._name = name
        self._config = config
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

    # Extra logic

    def software_controlled_run(self, acquisition_number, polling_time):
        # Loop over acquisitions
        for _ in range(acquisition_number):
            # Start and wait
            try:
                self.start_acquisition()
                while self.is_acquiring():
                    gevent.sleep(polling_time)
            # Stop in any case
            finally:
                self.stop_acquisition()
            # Send the data
            yield (self.get_acquisition_data(),
                   self.get_acquisition_statistics())

    def hardware_controlled_run(self, acquisition_number, polling_time):
        # Start acquisition
        try:
            self.start_acquisition()
            sent = current = 0
            # Loop over polled commands
            while not (sent == current == acquisition_number):
                # Poll data
                current, data, statistics = self.poll_data()
                points = range(sent, sent + len(data))
                sent += len(data)
                # Check data integrity
                if sorted(data) != sorted(statistics) != points:
                    raise RuntimeError(
                        'The polled data overlapped during the acquisition')
                # Send the data
                for n in points:
                    yield data[n], statistics[n]
                # Sleep
                if not points:
                    gevent.sleep(polling_time)
        # Stop in any case
        finally:
            self.stop_acquisition()

    def run_software_acquisition(self, acquisition_number,
                                 acquisition_time=1., polling_time=0.1):
        # Trigger mode
        self.set_trigger_mode(TriggerMode.SOFTWARE)
        # Preset mode
        self.set_preset_mode(PresetMode.REALTIME, acquisition_time)
        # Run acquisition
        data, statistics = zip(*self.software_controlled_run(
            acquisition_number, polling_time))
        # Return result
        return list(data), list(statistics)

    def run_gate_acquisition(self, acquisition_number,
                             block_size=None, polling_time=0.1):
        # Trigger mode
        self.set_trigger_mode(TriggerMode.GATE)
        # Acquisition number
        self.set_hardware_points(acquisition_number)
        # Block size
        self.set_block_size(block_size)
        # Run acquisition
        data, statistics = zip(*self.hardware_controlled_run(
            acquisition_number, polling_time))
        # Return result
        return list(data), list(statistics)

    def run_synchronized_acquisition(self, acquisition_number,
                                     block_size=None, polling_time=0.1):
        # Trigger mode
        self.set_trigger_mode(TriggerMode.SYNC)
        # Acquisition number
        self.set_hardware_points(acquisition_number+1)
        # Block size
        self.set_block_size(block_size)
        # Create generator
        data_generator = self.hardware_controlled_run(
            acquisition_number+1, polling_time)
        # Discard first point
        next(data_generator)
        # Get all the points
        data, statistics = zip(*data_generator)
        # Return result
        return list(data), list(statistics)
