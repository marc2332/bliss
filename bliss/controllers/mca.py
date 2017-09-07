"""Base class and enumerations for multichannel analyzers."""

# Imports
import time
import enum


# Enums

Brand = enum.Enum(
    'Brand',
    'XIA OCEAN_OPTICS ISG HAMAMATSU AMPTEK VANTEC CANBERRA RONTEC')

DetectorType = enum.Enum(
    'DetectorType',
    'FALCONX1 FALCONX4 FALCONX8 XMAP MERCURY MERCURY4 MICRO_DXP DXP_2X '
    'MAYA2000 MUSST_MCA MCA8000D DSA1000 MULTIMAX')

AcquisitionMode = enum.Enum(
    'AcquisitionMode',
    'MCA_NORMAL MCA_MAPPING SCA_MAPPING LIST_MODE SCA_HARD')

TriggerMode = enum.Enum(
    'TriggerMode',
    'INTERNAL SOFTWARE EXTERNAL_GATE EXTERNAL_MULTI_GATE '
    'EXTERNAL_MULTI_TRIGGER')

PresetMode = enum.Enum(
    'PresetMode',
    'NONE REAL_TIME LIVE_TIME')


# Base class

class BaseMCA(object):
    """Generic MCA controller."""

    def __init__(self, name, config):
        self.name = name
        self.config = config

    # Information

    def get_detector_brand(self):
        raise NotImplementedError

    def get_detector_type(self):
        raise NotImplementedError

    def get_element_count(self):
        raise NotImplementedError

    # Modes

    def get_supported_preset_modes(self):
        raise NotImplementedError

    def set_preset_mode(self, mode, *args):
        raise NotImplementedError

    def get_supported_acquisition_modes(self):
        raise NotImplementedError

    def set_acquisition_mode(self, mode):
        raise NotImplementedError

    def get_supported_trigger_mode(self):
        raise NotImplementedError

    def set_trigger_mode(self, mode):
        raise NotImplementedError

    # Settings

    def has_calibration(self):
        raise NotImplementedError

    def get_calibration_type(self):
        raise NotImplementedError

    def set_spectrum_range(self, first, last):
        raise NotImplementedError

    # Acquisition

    def prepare_acquisition(self):
        raise NotImplementedError

    def start_acquisition(self):
        raise NotImplementedError

    def stop_acquisition(self):
        raise NotImplementedError

    def get_acquisition_status(self):
        raise NotImplementedError

    def get_acquisition_data(self):
        raise NotImplementedError

    # Extra logic

    def run_single_acquisition(self, acquisition_time=1.):
        self.prepare_acquisition()
        self.start_acquisition()
        time.sleep(acquisition_time)
        self.stop_acquisition()
        return self.get_acquisition_data()
