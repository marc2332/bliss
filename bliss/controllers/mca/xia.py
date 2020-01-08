# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Controller classes for XIA multichannel analyzer"""

# Imports
from bliss.common.logtools import log_error, log_debug
from bliss.common import event
from bliss.config.beacon_object import BeaconObject

from bliss.comm import rpc
from .base import (
    BaseMCA,
    Brand,
    DetectorType,
    PresetMode,
    Stats,
    TriggerMode,
    AcquisitionMode,
    MCABeaconObject,
)

from bliss import global_map

# MCABeaconObject
class XIABeaconObject(MCABeaconObject):

    # Config / Settings
    @BeaconObject.property(priority=1, must_be_in_config=True, only_in_config=True)
    def url(self):
        return self.mca._url

    @url.setter
    def url(self, url):
        self.mca._url = url

    @BeaconObject.property(priority=2, must_be_in_config=True, only_in_config=True)
    def configuration_directory(self):
        return self.mca._config_dir

    @configuration_directory.setter
    def configuration_directory(self, config_dir):
        self.mca._config_dir = config_dir

    @BeaconObject.property(priority=3, must_be_in_config=True, only_in_config=True)
    def default_configuration(self):
        return self.mca._default_config

    @default_configuration.setter
    def default_configuration(self, config_file):
        self.mca._default_config = config_file


# Mercury controller
class BaseXIA(BaseMCA):
    """Base controller class for the XIA MCAs.

    This includes the following equipments:
    - Mercury
    - Mercury-4
    - XMAP
    - FalconX
    - FalconX-4
    - FalconX-8

    The configuration methods are expected to be called in the following order:
    - load_configuration
    - trigger_mode
    - preset_mode (for SOFTWARE trigger mode)
    - preset_value
    - hardware_points (for SYNC and GATE trigger modes)
    - block_size (for SYNC and GATE trigger modes)
    """

    def __init__(self, name, config, beacon_obj_class=XIABeaconObject):
        self._proxy = None
        super().__init__(name, config, beacon_obj_class=beacon_obj_class)
        global_map.register(self, parents_list=["mca"], tag=f"XiaMca:{self.name}")

    # Config / Settings
    @property
    def url(self):
        return self.beacon_obj.url

    @url.setter
    def url(self, url):
        self.beacon_obj.url = url

    @property
    def configuration_directory(self):
        return self.beacon_obj.configuration_directory

    @configuration_directory.setter
    def configuration_directory(self, config_dir):
        self.beacon_obj.configuration_directory = config_dir

    @property
    def default_configuration(self):
        return self.beacon_obj.default_configuration

    @default_configuration.setter
    def default_configuration(self, config_file):
        self.beacon_obj.default_configuration = config_file

    # Life cycle

    def initialize_attributes(self):
        self._proxy = None
        self._current_config = self.settings.get(
            "current_configuration", self._default_config
        )
        self._gate_master = self.config.get("gate_master", None)
        self._trigger_mode = TriggerMode.SOFTWARE

    def initialize_hardware(self):
        self._proxy = rpc.Client(self._url)
        event.connect(self._proxy, "data", self._event)
        global_map.register(self._proxy, parents_list=[self], tag="comm")
        # try:
        print(f"Loading {self.name} config {self._current_config}")
        self.load_configuration(self._current_config)
        # except:
        #    print("Loading config failed !!")

    def _event(self, value, signal):
        return event.send(self, signal, value)

    def finalize(self):
        self._proxy.close()
        event.disconnect(self._proxy, "data", self._event)

    def __info__(self):
        info_str = super().__info__()
        info_str += "XIA:\n"
        info_str += f"    configuration file:\n"
        info_str += f"      - default : {self.default_configuration}\n"
        info_str += f"      - current : {self.current_configuration}\n"

        return info_str

    # Configuration

    def _set_current_config(self, filename):
        self._current_config = filename
        # self._settings["current_configuration"] = filename
        self.beacon_obj._settings["current_configuration"] = filename

    @property
    def current_configuration(self):
        return self._current_config

    @property
    def configured(self):
        """Whether the hardware is properly configured or not."""
        return bool(self._current_config)

    @property
    def available_configurations(self):
        """List of all available configurations in the configuration directory.

        The returned filenames can be fetched for inspection using the
        get_configuration method.
        """
        return self._proxy.get_config_files(self._config_dir)

    @property
    def current_configuration_values(self):
        """The current configuration values.

        The returned object is an ordered dict of <section_name: list> where
        each item in the list is an ordered dict of <key: value>.
        """
        if not self._current_config:
            return None
        return self.fetch_configuration_values(self._current_config)

    def fetch_configuration_values(self, filename):
        """Fetch the configuration values corresponding to the given filename.

        The returned object is an ordered dict of <section_name: list> where
        each item in the list is an ordered dict of <key: value>.
        """
        return self._proxy.get_config(self._config_dir, filename)

    def load_configuration(self, filename):
        """Load the configuration.

        The filename is relative to the configuration directory.
        """
        try:
            self._proxy.init(self._config_dir, filename)
            self._proxy.start_system()  # Takes about 5 seconds
            self._run_checks()
        except:
            self._set_current_config(None)
            raise
        else:
            self._set_current_config(filename)

    def reload_configuration(self):
        """Force a reload of the current configuration.

        Useful when the file has changed or when the hardware or hardware
        server have been restarted.
        """
        if self._current_config:
            raise ValueError("No valid current configuration")
        self.load_configuration(self._current_config)

    def reload_default(self):
        self.load_configuration(self._default_config)

    def _run_checks(self):
        """Make sure the configuration corresponds to a mercury.

        - One and only one detector (hardware controller)
        - At least one acquisition module
        - At least one detector channel (a.k.a as element)
        """
        detectors = self._proxy.get_detectors()
        assert len(detectors) >= 1
        modules = self._proxy.get_modules()
        assert len(modules) >= 1
        channels = self._proxy.get_channels()
        assert len(channels) >= 1
        self._run_type_specific_checks()

    def _run_type_specific_checks(self):
        """Extra checks to be performed for the corresponding
        detector type (Mercury, Xmap, FalconX, etc.).
        """
        raise NotImplementedError

    # Settings

    @property
    def spectrum_size(self):
        return int(self._proxy.get_acquisition_value("number_mca_channels"))

    @spectrum_size.setter
    def spectrum_size(self, size):
        log_debug(self, f"set spectrum_size to {size}")
        self._proxy.set_acquisition_value("number_mca_channels", size)
        self._proxy.apply_acquisition_values()

    # Buffer settings

    @property
    def hardware_points(self):
        mapping = int(self._proxy.get_acquisition_value("mapping_mode"))
        if mapping == 0:
            return 1
        num = self._proxy.get_acquisition_value("num_map_pixels")
        return int(num)

    @hardware_points.setter
    def hardware_points(self, value):
        log_debug(self, f"set hardware_points to {value}")
        # Invalid argument
        if value < 1:
            raise ValueError("Acquisition number should be strictly positive")
        mapping = int(self._proxy.get_acquisition_value("mapping_mode"))
        # MCA mode
        if mapping == 0 and value not in (None, 1):
            raise ValueError("None and 1 are the only valid values in MCA mode")
        elif mapping == 0:
            return
        # Configure
        self._proxy.set_acquisition_value("num_map_pixels", value)
        # Apply
        self._proxy.apply_acquisition_values()

    @property
    def block_size(self):
        mapping = int(self._proxy.get_acquisition_value("mapping_mode"))
        if mapping == 0:
            return 1
        size = self._proxy.get_acquisition_value("num_map_pixels_per_buffer")
        return int(size)

    @block_size.setter
    def block_size(self, value=None):
        log_debug(self, f"set block_size to {value}")
        mapping = int(self._proxy.get_acquisition_value("mapping_mode"))
        # MCA mode
        if mapping == 0 and value not in (None, 1):
            raise ValueError("None and 1 are the only valid values in MCA mode")
        elif mapping == 0:
            return
        # Set the default value
        if value is None:
            self._proxy.set_maximum_pixels_per_buffer()
        # Set the specified value
        else:
            self._proxy.set_acquisition_value("num_map_pixels_per_buffer", value)
        # Apply
        self._proxy.apply_acquisition_values()

    # Acquisition

    def start_acquisition(self):
        # Make sure the acquisition is stopped first
        log_debug(self, "start_acquisition")
        self._proxy.stop_run()
        self._proxy.start_run()

    def start_hardware_reading(self):
        self._proxy.start_hardware_reading()

    def wait_hardware_reading(self):
        self._proxy.wait_hardware_reading()

    def trigger(self):
        log_debug(self, "trigger")
        self._proxy.trigger()

    def stop_acquisition(self):
        log_debug(self, "stop_acquisition")
        self._proxy.stop_run()

    def is_acquiring(self):
        return self._proxy.is_running()

    def get_acquisition_data(self):
        log_debug(self, "get_acquisition_data")
        spectrums = self._proxy.get_spectrums()
        return self._convert_spectrums(spectrums)

    def get_acquisition_statistics(self):
        log_debug(self, "get_acquisition_statistics")
        stats = self._proxy.get_statistics()
        return self._convert_statistics(stats)

    def poll_data(self):
        log_debug(self, "poll_data")
        current, spectrums, statistics = self._proxy.synchronized_poll_data()
        spectrums = dict(
            (key, self._convert_spectrums(value)) for key, value in spectrums.items()
        )
        statistics = dict(
            (key, self._convert_statistics(value)) for key, value in statistics.items()
        )
        return current, spectrums, statistics

    def _convert_spectrums(self, spectrums):
        return spectrums

    def _convert_statistics(self, stats):
        return dict((k, Stats(*v)) for k, v in stats.items())

    # Infos

    @property
    def detector_brand(self):
        return Brand.XIA

    @property
    def detector_type(self):
        value = self._proxy.get_module_type().upper()
        if value == "FALCONXN":
            return DetectorType.FALCONX
        return getattr(DetectorType, value)

    @property
    def elements(self):
        return self._proxy.get_channels()

    # Modes

    @property
    def supported_preset_modes(self):
        return [
            PresetMode.NONE,
            PresetMode.REALTIME,
            PresetMode.LIVETIME,
            PresetMode.EVENTS,
            PresetMode.TRIGGERS,
        ]

    @property
    def preset_mode(self):
        mode = self._proxy.get_acquisition_value("preset_type")
        ptype = {
            0: PresetMode.NONE,
            1: PresetMode.REALTIME,
            2: PresetMode.LIVETIME,
            3: PresetMode.EVENTS,
            4: PresetMode.TRIGGERS,
        }[int(mode)]
        return ptype

    @preset_mode.setter
    def preset_mode(self, mode):
        log_debug(self, f"set preset_mode to {mode}")
        # Cast arguments
        if mode is None:
            mode = PresetMode.NONE
        # Check arguments
        if mode not in self.supported_preset_modes:
            raise ValueError("{!s} preset mode not supported".format(mode))
        # Convert
        pvalue = {
            PresetMode.NONE: 0,
            PresetMode.REALTIME: 1,
            PresetMode.LIVETIME: 2,
            PresetMode.EVENTS: 3,
            PresetMode.TRIGGERS: 4,
        }[mode]
        # Configure
        self._proxy.set_acquisition_value("preset_type", pvalue)
        self._proxy.apply_acquisition_values()

    @property
    def preset_value(self):
        value = self._proxy.get_acquisition_value("preset_value")
        # Return cast value depending on mode
        return self.__preset_value_cast(value)

    @preset_value.setter
    def preset_value(self, value):
        log_debug(self, f"set preset_value to {value}")
        mode = self.preset_mode
        # Cast arguments depending on preset mode
        pvalue = self.__preset_value_cast(value)
        # Configure
        self._proxy.set_acquisition_value("preset_value", pvalue)
        self._proxy.apply_acquisition_values()

    def __preset_value_cast(self, value):
        mode = self.preset_mode
        pcast = {
            PresetMode.NONE: lambda x: 0,
            PresetMode.REALTIME: float,
            PresetMode.LIVETIME: float,
            PresetMode.EVENTS: int,
            PresetMode.TRIGGERS: int,
        }[mode]
        return pcast(value)

    @property
    def supported_trigger_modes(self):
        return [TriggerMode.SOFTWARE, TriggerMode.SYNC, TriggerMode.GATE]

    @property
    def trigger_mode(self):
        return self._trigger_mode

    @trigger_mode.setter
    def trigger_mode(self, mode):
        log_debug(self, f"set trigger_mode to {mode}")
        # Cast arguments
        if mode is None:
            mode = TriggerMode.SOFTWARE
        # Check arguments
        if mode not in self.supported_trigger_modes:
            raise ValueError("{!s} trigger mode not supported".format(mode))
        # XMAP Trigger
        if self.detector_type == DetectorType.XMAP:
            self.set_xmap_gate_master(mode)
        # Configure mapping mode and gate ignore
        gate_ignore = 0 if mode == TriggerMode.GATE else 1
        mapping_mode = 0 if mode == TriggerMode.SOFTWARE else 1
        self._proxy.set_acquisition_value("gate_ignore", gate_ignore)
        self._proxy.set_acquisition_value("mapping_mode", mapping_mode)
        # Configure advance mode
        if mode != TriggerMode.SOFTWARE:
            gate = 1
            self._proxy.set_acquisition_value("pixel_advance_mode", gate)
        self._proxy.apply_acquisition_values()
        self._trigger_mode = mode

    def set_xmap_gate_master(self, mode):
        # Add extra logic for external and gate trigger mode
        if mode in (TriggerMode.SYNC, TriggerMode.GATE):
            available = self._proxy.get_trigger_channels()
            # Check available trigger channels
            if not available:
                raise ValueError("This configuration does not support trigger signals")
            channel = self._gate_master
            # Check channel argument
            if channel is None:
                channel = available[0]
            elif channel not in available:
                raise ValueError(
                    "The given gate master channel is not a valid trigger channel"
                )
            # Set gate master parameter
            log_debug(self, f"set xmap gate_master to {channel}")
            self._proxy.set_acquisition_value("gate_master", True, channel)
            self._gate_master = channel

    # Modes
    def set_hardware_scas(self, scas):
        raise NotImplementedError


# Specific XIA classes


class XIA(BaseXIA):
    """Generic controller class for a XIA MCA."""

    def _run_type_specific_checks(self):
        assert self.detector_type in DetectorType
        assert all(e in range(16) for e in self.elements)


class Mercury(BaseXIA):
    """Controller class for the Mercury (a XIA MCA)."""

    def _run_type_specific_checks(self):
        assert self.detector_type == DetectorType.MERCURY
        assert all(e in range(4) for e in self.elements)

    @property
    def supported_acquisition_modes(self):
        return [AcquisitionMode.MCA, AcquisitionMode.HWSCA]

    def set_hardware_scas(self, scas):
        log_debug(self, "set_hardware_scas")
        det_scas = dict()
        for (det, start, stop) in scas:
            if det not in det_scas:
                det_scas[det] = list()
            det_scas[det].append((start, stop))
        for det, scalist in det_scas.items():
            ndetsca = len(scalist)
            self._proxy.set_acquisition_value("number_of_scas", ndetsca, det)
            for (isca, (start, stop)) in enumerate(scalist):
                log_debug(
                    self,
                    f"setting hwsca det#{det} isca#{isca} start#{start} stop#{stop}",
                )
                self._proxy.set_acquisition_value("sca{:d}_lo".format(isca), start, det)
                self._proxy.set_acquisition_value("sca{:d}_hi".format(isca), stop, det)
            self._proxy.set_acquisition_value("trigger_output", 1, det)
            self._proxy.set_acquisition_value("livetime_output", 1, det)
        self._proxy.apply_acquisition_values()

    def reset_hardware_scas(self):
        for det in self.elements:
            self._proxy.set_acquisition_value("number_of_scas", 0, det)
            self._proxy.set_acquisition_value("trigger_output", 0, det)
            self._proxy.set_acquisition_value("livetime_output", 0, det)
        self._proxy.apply_acquisition_values()

    def get_hardware_scas(self):
        scas = list()
        for det in self.elements:
            nsca = self._proxy.get_acquisition_value("number_of_scas", det)
            for isca in range(int(nsca)):
                start = self._proxy.get_acquisition_value(
                    "sca{:d}_lo".format(isca), det
                )
                stop = self._proxy.get_acquisition_value("sca{:d}_hi".format(isca), det)
                scas.append((det, int(start), int(stop)))
        return scas


class XMAP(BaseXIA):
    """Controller class for the XMAP (a XIA MCA)."""

    def _run_type_specific_checks(self):
        assert self.detector_type == DetectorType.XMAP
        assert all(e in range(16) for e in self.elements)

    @property
    def gate_master(self):
        return self._gate_master


class FalconX(BaseXIA):
    """Controller class for the FalconX (a XIA MCA)."""

    def _run_type_specific_checks(self):
        assert self.detector_type == DetectorType.FALCONX
        assert all(e in range(8) for e in self.elements)

    def __info__(self):
        info_str = super().__info__()
        info_str += "\nFALCONX:\n"

        info_str += f"    address: {self.url}\n"
        return info_str
