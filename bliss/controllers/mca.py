"""Base class and enumerations for multichannel analyzers."""

# Imports
import time
import enum
import collections


# Enums

Brand = enum.Enum(
    'Brand',
    'XIA OCEAN_OPTICS ISG HAMAMATSU AMPTEK VANTEC CANBERRA RONTEC')

DetectorType = enum.Enum(
    'DetectorType',
    'FALCONX1 FALCONX4 FALCONX8 XMAP MERCURY MERCURY4 MICRO_DXP DXP_2X '
    'MAYA2000 MUSST_MCA MCA8000D DSA1000 MULTIMAX')

TriggerMode = enum.Enum(
    'TriggerMode',
    'SOFTWARE EXTERNAL GATE')

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
    def element_count(self):
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

    # Acquisition number (number of points in acquisition)

    @property
    def acquisition_number(self):
        raise NotImplementedError

    def set_acquisition_number(self, value):
        raise NotImplementedError

    @property
    def block_size(self):
        raise NotImplementedError

    def set_block_size(self, value=None):
        raise NotImplementedError

    @property
    def multiple_acquisition(self):
        return self.acquisition_number > 1

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

    def run_single_acquisition(self, acquisition_time=1., polling_time=0.1):
        # Acquisition number
        self.set_acquisition_number(1)
        # Trigger mode
        self.set_trigger_mode(None)
        # Preset mode
        realtime = PresetMode.REALTIME in self.supported_preset_modes
        if realtime:
            self.set_preset_mode(PresetMode.REALTIME, acquisition_time)
        else:
            self.set_preset_mode(None)
        # Start and wait
        self.start_acquisition()
        if realtime:
            while self.is_acquiring():
                time.sleep(polling_time)
        else:
            time.sleep(acquisition_time)
        # Stop and return data
        self.stop_acquisition()
        return self.get_acquisition_data(), self.get_acquisition_statistics()

    def run_external_acquisition(self, acquistion_time=None, polling_time=0.1):
        # Acquisition number
        self.set_acquisition_number(1)
        # Trigger mode
        mode = TriggerMode.EXTERNAL if acquistion_time else TriggerMode.GATE
        self.set_trigger_mode(mode)
        # Preset mode
        if acquistion_time:
            self.set_preset_mode(PresetMode.REALTIME, acquistion_time)
        else:
            self.set_preset_mode(None)
        # Start and wait
        self.start_acquisition()
        get_realtime = lambda: self.get_acquisition_statistics()[0].realtime
        previous, current = 0., get_realtime()
        while current == 0. or previous != current:
            time.sleep(polling_time)
            previous, current = current, get_realtime()
        # Stop and return data
        self.stop_acquisition()
        return self.get_acquisition_data(), self.get_acquisition_statistics()

    def run_multiple_acquisitions(self, acquisition_number,
                                  block_size=None, gate=False, polling_time=0.1):
        # Acquisition number
        self.set_acquisition_number(acquisition_number)
        self.set_block_size(block_size)
        # Trigger mode
        mode = TriggerMode.GATE if gate else TriggerMode.EXTERNAL
        self.set_trigger_mode(mode)
        # Preset mode
        self.set_preset_mode(None)
        # Start and wait
        self.start_acquisition()
        current, data, statistics = self.poll_data()
        while current != self.acquisition_number:
            time.sleep(polling_time)
            current, extra_data, extra_statistics = self.poll_data()
            data.update(extra_data)
            statistics.update(extra_statistics)
        # Stop and return data
        self.stop_acquisition()
        return data, statistics
