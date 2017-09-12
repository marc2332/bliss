"""Controller classes for XIA multichannel analyzer"""

# Imports
import zerorpc
import msgpack_numpy

from .mca import BaseMCA, Brand, DetectorType

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

    # Acquisition

    def prepare_acquisition(self):
        pass

    def start_acquisition(self):
        self._proxy.start_run(0)

    def stop_acquisition(self):
        self._proxy.stop_run(0)

    def get_acquisition_status(self):
        return ""

    def get_acquisition_data(self):
        return [self._proxy.get_run_data(0)]

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
