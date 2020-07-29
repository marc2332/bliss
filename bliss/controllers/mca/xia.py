# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Controller classes for XIA multichannel analyzer"""

# Imports
from bliss.common.logtools import log_debug
from bliss.shell.standard import lprint
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
    TriggerModeNames,
    AcquisitionMode,
    MCABeaconObject,
)

from bliss import global_map

from bliss.shell.cli.user_dialog import UserChoice
from bliss.shell.cli.pt_widgets import display


# Logger to use at session startup.
# To log after session startup: use log_debug(self, <msg>)
import logging

logger = logging.getLogger(__name__)


# MCABeaconObject
class XIABeaconObject(MCABeaconObject):

    # Config / Settings
    url = BeaconObject.config_getter("url")
    configuration_directory = BeaconObject.config_getter("configuration_directory")
    default_configuration = BeaconObject.config_getter("default_configuration")

    @BeaconObject.property(priority=1)
    def current_configuration(self):
        # we get there if the configuration was not changed ???
        return self.default_configuration

    @current_configuration.setter
    def current_configuration(self, filename):
        if filename is not None:
            self.mca._load_configuration(filename)


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
        # global_map.register(self, parents_list=["mca"], tag=f"XiaMca:{self.name}")
        global_map.register(
            self._proxy, parents_list=[self, "comms"], tag=f"rpcXia:{self.name}"
        )
        self._last_pixel_triggered = -1

    # Config / Settings
    @property
    def url(self):
        return self.beacon_obj.url

    @property
    def configuration_directory(self):
        return self.beacon_obj.configuration_directory

    @property
    def default_configuration(self):
        return self.beacon_obj.default_configuration

    # Life cycle

    def initialize_attributes(self):
        """ Called at session startup.
        """
        logger.debug("initialize_attributes()")
        self._proxy = None
        self._gate_master = self.config.get("gate_master", None)
        self._trigger_mode = TriggerMode.SOFTWARE

    def initialize_hardware(self):
        """ Called at session startup
        """
        logger.debug("initialize_hardware()")
        self._proxy = rpc.Client(self.beacon_obj.url)
        event.connect(self._proxy, "data", self._event)
        event.connect(self._proxy, "current_pixel", self._current_pixel_event)
        # global_map.register(self._proxy, parents_list=[self], tag="comm")
        try:
            # Getting the current configuration will
            # Call load_configuration on the first peers.
            self.beacon_obj.current_configuration
        except Exception:
            print("Loading config failed !!")
        logger.debug("current_configuration=%s", self.beacon_obj.current_configuration)

    def _event(self, value, signal):
        return event.send(self, signal, value)

    def finalize(self):
        log_debug(self, "  close proxy")
        self._proxy.close()
        event.disconnect(self._proxy, "data", self._event)
        event.disconnect(self._proxy, "current_pixel", self._current_pixel_event)

    def __info__(self):
        info_str = super().__info__()
        info_str += "XIA:\n"
        info_str += "    configuration directory:\n"
        cdir = self.configuration_directory.replace("\\\\", "\\")
        info_str += f"      - {cdir}\n"
        info_str += "    configuration files:\n"
        info_str += f"      - default : {self.default_configuration}\n"
        info_str += f"      - current : {self.current_configuration}\n"

        return info_str

    # Configuration
    @property
    def current_configuration(self):
        return self.beacon_obj.current_configuration

    @property
    def configured(self):
        """Whether the hardware is properly configured or not."""
        return bool(self.beacon_obj.current_configuration)

    @property
    def available_configurations(self):
        """List of all available configurations in the configuration directory.

        The returned filenames can be fetched for inspection using the
        get_configuration method.
        """
        return self._proxy.get_config_files(self.beacon_obj.configuration_directory)

    @property
    def current_configuration_values(self):
        """The current configuration values.

        The returned object is an ordered dict of <section_name: list> where
        each item in the list is an ordered dict of <key: value>.
        """
        if not self.current_configuration:
            return None
        return self.fetch_configuration_values(self.current_configuration)

    def fetch_configuration_values(self, filename):
        """Fetch the configuration values corresponding to the given filename.

        The returned object is an ordered dict of <section_name: list> where
        each item in the list is an ordered dict of <key: value>.
        """
        return self._proxy.get_config(self.beacon_obj.configuration_directory, filename)

    def load_configuration(self, filename):
        """ Assign .current_configuration and call _load_configuration()
        """
        self.beacon_obj.current_configuration = filename

    def _load_configuration(self, filename):
        """Load the configuration.
        Called once at session startup and then on demand.
        The filename is relative to the configuration directory.
        """
        try:
            lprint(f"Loading configuration '{filename}'")
            self._proxy.init(self.beacon_obj.configuration_directory, filename)
            self._proxy.start_system()  # Takes about 5 seconds
            self._run_checks()
            logger.debug("load_configuration: %s loaded", filename)
        except Exception:
            self.beacon_obj.current_configuration = None
            raise

    def reload_configuration(self):
        """Force a reload of the current configuration.

        Useful when the file has changed or when the hardware or hardware
        server have been restarted.
        """
        log_debug(self, "reload_configuration()")
        if self.current_configuration:
            raise ValueError("No valid current configuration")
        self.load_configuration(self.current_configuration)

    def reload_default(self):
        """ Load configuration definded in YAML config.
        """
        self.load_configuration(self.default_configuration)

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

    # SPECTRUM SIZE
    @property
    def spectrum_size(self):
        return int(self._proxy.get_acquisition_value("number_mca_channels"))

    @spectrum_size.setter
    def spectrum_size(self, size):
        log_debug(self, "set spectrum_size to %s", size)
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
        log_debug(self, "set hardware_points to %s", value)
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
        log_debug(self, "set block_size to %s", value)
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
        """ ??? """
        log_debug(self, "start_acquisition")
        # Make sure the acquisition is stopped first
        self._proxy.stop_run()
        self._last_pixel_triggered = -1
        self._proxy.start_run()

    def start_hardware_reading(self):
        """ ??? """
        log_debug(self, "start_hardware_reading")
        self._proxy.start_hardware_reading()

    def wait_hardware_reading(self):
        """ ??? """
        log_debug(self, "wait_hardware_reading")
        self._proxy.wait_hardware_reading()

    def trigger(self):
        log_debug(self, "trigger")
        self._proxy.trigger()

    def stop_acquisition(self):
        log_debug(self, "stop_acquisition")
        self._proxy.stop_run()

    def is_acquiring(self):
        log_debug(self, "is_acquiring")
        return self._proxy.is_running()

    def get_acquisition_data(self):
        log_debug(self, "get_acquisition_data")
        spectrums = self._proxy.get_spectrums()
        return self._convert_spectrums(spectrums)

    def get_acquisition_statistics(self):
        stats = self._proxy.get_statistics()
        log_debug(self, "get_acquisition_statistics() ->", stats)
        log_debug(self, f"STATS = {stats}")
        return self._convert_statistics(stats)

    def poll_data(self):
        current, spectrums, statistics = self._proxy.synchronized_poll_data()
        spectrums = dict(
            (key, self._convert_spectrums(value)) for key, value in spectrums.items()
        )
        statistics = dict(
            (key, self._convert_statistics(value)) for key, value in statistics.items()
        )
        log_debug(self, "poll_data() -- current={}", current)
        # log_debug(self, "spectrums={}", spectrums)
        # log_debug(self, "statistics={}", statistics)

        return current, spectrums, statistics

    def _convert_spectrums(self, spectrums):
        return spectrums

    def _convert_statistics(self, stats):
        return dict((k, Stats(*v)) for k, v in stats.items())

    def _current_pixel_event(self, value, signal):
        if value != self._last_pixel_triggered:
            log_debug(self, "last pixel triggered = %d", value)
        self._last_pixel_triggered = value

    @property
    def last_pixel_triggered(self):
        return self._last_pixel_triggered

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

    # Preset modes (preset_type)

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
        log_debug(self, "set preset_mode (preset_type) to %s", mode)
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
        log_debug(self, "set preset_value to %s", value)
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
        """Set a combination of parameters to reflect <mode> triggering
        mode:
        * 'mapping mode'
        * 'gate ignore'
        * 'advance mode'
        * 'xmap_gate_master'
        """
        log_debug(self, "try to set trigger_mode to '%s'", mode)

        # Cast argument
        if mode is None:
            mode = TriggerMode.SOFTWARE
        if type(mode) == str:
            try:
                mode = TriggerModeNames[mode]
            except Exception:
                raise ValueError("{!s} trigger mode not supported".format(mode))

        # Check argument
        if mode not in self.supported_trigger_modes:
            raise ValueError("{!s} trigger mode not supported".format(mode))

        log_debug(self, "set trigger_mode to '%s'", mode)

        # XMAP Trigger: set trigger mode on MASTER
        # (possibly many cards -> can be another det number)
        if self.detector_type == DetectorType.XMAP:
            self.set_xmap_gate_master(mode)

        # Configure 'mapping mode' and 'gate ignore'
        gate_ignore = 0 if mode == TriggerMode.GATE else 1
        mapping_mode = 0 if mode == TriggerMode.SOFTWARE else 1
        self._proxy.set_acquisition_value("gate_ignore", gate_ignore)
        self._proxy.set_acquisition_value("mapping_mode", mapping_mode)

        # Configure 'advance mode'
        if mode != TriggerMode.SOFTWARE:
            gate = 1
            self._proxy.set_acquisition_value("pixel_advance_mode", gate)
        self._proxy.apply_acquisition_values()

        self._trigger_mode = mode

    def set_xmap_gate_master(self, mode):
        log_debug(self, "set_xmap_gate_master(mode=%s)", mode)
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
            log_debug(self, "set xmap gate_master to %s", channel)
            self._proxy.set_acquisition_value("gate_master", True, channel)
            self._gate_master = channel

    # Modes
    def set_hardware_scas(self, scas):
        raise NotImplementedError

    # Dialogs to configure XIA device
    def select_config(self):
        config_list = self.available_configurations
        dlg_list = list(zip(config_list, config_list))
        dlg = UserChoice(label="Configuration File", values=dlg_list)
        self.load_configuration(display(dlg))

    def select_trig(self):
        triggers_list = [ttt.name for ttt in TriggerMode]
        dlg_list = list(zip(triggers_list, ["1 - SOFTWARE", "2 - SYNC", "3 - GATE"]))
        dlg = UserChoice(label="Trigger Mode", values=dlg_list)
        ans = display(dlg)
        print(f"user choose '{ans}'")
        self.trigger_mode = ans

    def select_preset_mode(self):
        preset_list = [ppp.name for ppp in self.supported_preset_modes]
        dlg_list = list(zip(preset_list, preset_list))
        dlg = UserChoice(label="Preset Mode", values=dlg_list)
        ans = display(dlg)
        print(f"user choose '{ans}'")
        self.preset_mode = ans


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
                    "setting hwsca det#%s isca#%s start#%s stop#%s",
                    det,
                    isca,
                    start,
                    stop,
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

    """
    MCA refresh period in seconds.
    This controls how often MCA updates are sent from the FalconXn to the client machine.
    Default: 0.1.
    Does not exist for xmap/mercury
    Must be lower than counting time.
    """

    @property
    def refresh_rate(self):
        return float(self._proxy.get_acquisition_value("mca_refresh"))

    @refresh_rate.setter
    def refresh_rate(self, rate):
        log_debug(self, "set refresh rate (mca_refresh to %g", rate)
        self._proxy.set_acquisition_value("mca_refresh", rate)
        self._proxy.apply_acquisition_values()
