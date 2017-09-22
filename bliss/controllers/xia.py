"""Controller classes for XIA multichannel analyzer"""

# Imports
from numbers import Number

import zerorpc
import msgpack_numpy

from .mca import BaseMCA, Brand, DetectorType, PresetMode, Stats, TriggerMode

# Patch msgpack
msgpack_numpy.patch()


# Mercury controller

class Mercury(BaseMCA):
    """Controller class for the Mercury (a XIA MCA).
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
        - One and only one acquisition module
        - One and only one detector channel (a.k.a as element)
        - By convention, the channel is numbered 0.
        """
        detectors = self._proxy.get_detectors()
        assert len(detectors) == 1
        modules = self._proxy.get_modules()
        assert len(modules) == 1
        channels = self._proxy.get_channels()
        assert len(channels) == 1
        assert channels == (0,)
        grouped_channels = self._proxy.get_grouped_channels()
        assert grouped_channels == ((0, ), )

    # Acquisition number

    @property
    def acquisition_number(self):
        mapping = int(self._proxy.get_acquisition_value('mapping_mode', 0))
        if mapping == 0:
            return 1
        # Should be:
        num = self._proxy.get_acquisition_value('num_map_pixels', 0)
        return int(num)

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
            self._proxy.set_acquisition_value('num_map_pixels', value)
        # Apply
        self._proxy.apply_acquisition_values()

    @property
    def block_size(self):
        pixels_per_buffer = self._proxy.get_acquisition_value(
            'num_map_pixels_per_buffer', 0)
        return int(pixels_per_buffer)

    def set_block_size(self, value=None):
        # Get default block size
        if value is None:
            self._proxy.set_acquisition_value('num_map_pixels_per_buffer', -1)
            value = min(
                self._proxy.get_acquisition_value('num_map_pixels_per_buffer', i)
                for i in range(self.element_count))
        # Set value
        self._proxy.set_acquisition_value('num_map_pixels_per_buffer', value)
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
        nb = len(spectrums)
        return [spectrums[i] for i in range(nb)]

    def get_acquisition_statistics(self):
        stats = self._proxy.get_statistics()
        nb = len(stats)
        return [Stats(*stats[i]) for i in range(nb)]

    def poll_data(self):
        return self._proxy.synchronized_poll_data()

    # Infos

    @property
    def detector_brand(self):
        return Brand.XIA

    @property
    def detector_type(self):
        return DetectorType.MERCURY

    @property
    def element_count(self):
        return 1

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

    def set_trigger_mode(self, mode):
        # Cast arguments
        if mode is None:
            mode = TriggerMode.SOFTWARE
        # Check arguments
        if mode not in self.supported_trigger_modes:
            raise ValueError('{!s} trigger mode not supported'.format(mode))
        if mode == TriggerMode.EXTERNAL and self.acquisition_number == 1:
            raise ValueError(
                'External trigger mode not supported in single acquisition mode')
        # Get hardware value
        gate_ignore = 0 if mode == TriggerMode.GATE else 1
        advance_mode = 0 if mode == TriggerMode.SOFTWARE else 1
        # Configure
        self._proxy.set_acquisition_value('gate_ignore', gate_ignore)
        self._proxy.set_acquisition_value('pixel_advance_mode', advance_mode)
        self._proxy.apply_acquisition_values()
