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
    def element_count(self):
        raise NotImplementedError

    # Modes

    @property
    def supported_preset_modes(self):
        raise NotImplementedError

    def set_preset_mode(self, mode, *args):
        raise NotImplementedError

    @property
    def supported_acquisition_modes(self):
        raise NotImplementedError

    def set_acquisition_mode(self, mode):
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
