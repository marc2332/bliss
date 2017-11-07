# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Controller classes for XIA multichannel analyzer"""

# Imports
from numbers import Number

import zerorpc
import msgpack_numpy

from .mca import BaseMCA, Brand, DetectorType, PresetMode, Stats, TriggerMode

# Patch msgpack
msgpack_numpy.patch()


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
    - set_acquisition_number
    - set_block_size (ignored for single acquisition)
    - set_trigger_mode
    - set_preset_mode (can be disabled using None)
    """

    # Life cycle

    def initialize_attributes(self):
        self._proxy = None
        self._current_config = None
        self._url = self._config['url']
        self._config_dir = self._config['configuration_directory']
        self._default_config = self._config['default_configuration']

    def initialize_hardware(self):
        self._proxy = zerorpc.Client(self._url)
        self.load_configuration(self._default_config)

    def finalize(self):
        self._proxy.close()

    # Configuration

    @property
    def current_configuration(self):
        """The current configuration filename loaded by the hardware."""
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
            self._current_config = None
            raise
        else:
            self._current_config = filename

    def _run_checks(self):
        """Make sure the configuration corresponds to a mercury.

        - One and only one detector (hardware controller)
        - At least one acquisition module
        - At least one detector channel (a.k.a as element)
        """
        detectors = self._proxy.get_detectors()
        assert len(detectors) == 1
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

    # Acquisition number

    @property
    def acquisition_number(self):
        mapping = int(self._proxy.get_acquisition_value('mapping_mode'))
        if mapping == 0:
            return 1
        num = self._proxy.get_acquisition_value('num_map_pixels')
        # The first acquistion will be discarded
        return int(num) - 1

    def set_acquisition_number(self, value):
        # Invalid argument
        if value < 1:
            raise ValueError('Acquisition number should be strictly positive')
        # Single mode
        if value == 1:
            self._proxy.set_acquisition_value('mapping_mode', 0)
        # Multiple mode
        else:
            self._proxy.set_acquisition_value('mapping_mode', 1)
            # The first acquisition will be discarded
            self._proxy.set_acquisition_value('num_map_pixels', value + 1)
        # Apply
        self._proxy.apply_acquisition_values()

    @property
    def block_size(self):
        size = self._proxy.get_acquisition_value('num_map_pixels_per_buffer')
        return int(size)

    def set_block_size(self, value=None):
        # Set the default value
        if value is None:
            self._proxy.set_maximum_pixels_per_buffer()
        # Set the specified value
        else:
            self._proxy.set_acquisition_value(
                'num_map_pixels_per_buffer', value)
        # Apply
        self._proxy.apply_acquisition_values()

    # Acquisition

    def start_acquisition(self):
        # Make sure the acquisition is stopped first
        self._proxy.stop_run()
        self._proxy.start_run()

    def stop_acquisition(self):
        self._proxy.stop_run()

    def is_acquiring(self):
        return self._proxy.is_running()

    def get_acquisition_data(self):
        spectrums = self._proxy.get_spectrums()
        return self._convert_spectrums(spectrums)

    def get_acquisition_statistics(self):
        stats = self._proxy.get_statistics()
        return self._convert_statistics(stats)

    def poll_data(self):
        current, spectrums, statistics = self._proxy.synchronized_poll_data()
        # The first acquisition is discarded
        spectrums = {key - 1: self._convert_spectrums(value)
                     for key, value in spectrums.items()
                     if key > 0}
        statistics = {key - 1: self._convert_statistics(value)
                      for key, value in statistics.items()
                      if key > 0}
        return current - 1, spectrums, statistics

    def _convert_spectrums(self, spectrums):
        return spectrums

    def _convert_statistics(self, stats):
        return {k: Stats(*v) for k, v in stats.items()}

    # Infos

    @property
    def detector_brand(self):
        return Brand.XIA

    @property
    def detector_type(self):
        value = self._proxy.get_module_type().upper()
        if value == 'FALCONXN':
            return DetectorType.FALCONX
        return getattr(DetectorType, value)

    @property
    def elements(self):
        return self._proxy.get_channels()

    # Modes

    @property
    def supported_preset_modes(self):
        return [PresetMode.NONE,
                PresetMode.REALTIME,
                PresetMode.LIVETIME,
                PresetMode.EVENTS,
                PresetMode.TRIGGERS]

    def set_preset_mode(self, mode, value=None):
        # Cast arguments
        if mode is None:
            mode = PresetMode.NONE
        # Check arguments
        if mode not in self.supported_preset_modes:
            raise ValueError('{!s} preset mode not supported'.format(mode))
        if mode == PresetMode.NONE and value is not None:
            raise TypeError(
                'Preset value should be None when no preset mode is set')
        if mode != PresetMode.NONE and not isinstance(value, Number):
            raise TypeError(
                'Preset value should be a number when a preset mode is set')
        # Get hardware values
        ptype, pcast = {
            PresetMode.NONE: (0, lambda x: 0),
            PresetMode.REALTIME: (1, float),
            PresetMode.LIVETIME: (2, float),
            PresetMode.EVENTS: (3, int),
            PresetMode.TRIGGERS: (4, int)}[mode]
        pvalue = pcast(value)
        # Configure
        self._proxy.set_acquisition_value('preset_type', ptype)
        self._proxy.set_acquisition_value('preset_value', pvalue)
        self._proxy.apply_acquisition_values()

    @property
    def supported_trigger_modes(self):
        return [TriggerMode.SOFTWARE,
                TriggerMode.EXTERNAL,
                TriggerMode.GATE]

    def set_trigger_mode(self, mode, channel=None):
        """Set the trigger mode.

        Warning: this method assumes the correct number of acquisition
        is already set correctly. If the number of acquistion changes,
        this methods needs to be reinvoked.
        """
        # Cast arguments
        if mode is None:
            mode = TriggerMode.SOFTWARE
        # Check arguments
        if mode not in self.supported_trigger_modes:
            raise ValueError('{!s} trigger mode not supported'.format(mode))
        if mode == TriggerMode.EXTERNAL and self.acquisition_number == 1:
            raise ValueError(
                'External trigger mode not supported for single acquisition')
        # XMAP Trigger
        if self.detector_type == DetectorType.XMAP:
            self.set_xmap_trigger_mode(mode, channel=channel)
        elif channel is not None:
            raise ValueError(
                'Channel argument can only provided for XMAP detector')
        # Configure gate ignore
        gate_ignore = 0 if mode == TriggerMode.GATE else 1
        self._proxy.set_acquisition_value('gate_ignore', gate_ignore)
        # Configure advance mode
        if self.acquisition_number > 1:
            soft, gate, sync = 0, 1, 2
            self._proxy.set_acquisition_value(
                'pixel_advance_mode',
                soft if mode == TriggerMode.SOFTWARE else gate)
        self._proxy.apply_acquisition_values()

    def set_xmap_trigger_mode(self, mode, channel=None):
        # Add extra logic for external and gate trigger mode
        if mode in (TriggerMode.EXTERNAL, TriggerMode.GATE):
            available = self._proxy.get_trigger_channels()
            # Check available trigger channels
            if not available:
                raise ValueError(
                    'This configuration does not support trigger signals')
            # Check channel argument
            if channel is not None and channel not in available:
                raise ValueError(
                    'The given channel is not a valid trigger channel')
            # Set default channel value
            if channel is None:
                channel = available[0]
            # Set gate master parameter
            self._proxy.set_acquisition_value('gate_master', True, channel)


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


class XMAP(BaseXIA):
    """Controller class for the XMAP (a XIA MCA)."""

    def _run_type_specific_checks(self):
        assert self.detector_type == DetectorType.XMAP
        assert all(e in range(16) for e in self.elements)


class FalconX(BaseXIA):
    """Controller class for the FalconX (a XIA MCA)."""

    def _run_type_specific_checks(self):
        assert self.detector_type == DetectorType.FALCONX
        assert all(e in range(8) for e in self.elements)
