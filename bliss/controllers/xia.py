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

    def __init__(self, name, config):
        """Initialize the controller."""
        super(Mercury, self).__init__(name, config)
        self.url = config['url']
        self.current_config = None
        self.config_dir = config['configuration_directory']
        self.default_config = config['default_configuration']
        self.proxy = zerorpc.Client(self.url)
        self.load_configuration(self.default_config)

    # Configuration

    def load_configuration(self, filename):
        """Load the configuration.

        The filename is relative to the configuration directory.
        """
        try:
            self.proxy.init(self.config_dir, filename)
            self.proxy.start_system()  # Takes about 5 seconds
            self.run_checks()
        except:
            self.current_config = None
            raise
        else:
            self.current_config = filename

    def get_available_configurations(self):
        """List all available configurations in the configuration directory.

        The returned filenames can be fetched for inspection using the
        get_configuration method.
        """
        return self.proxy.get_config_files(self.config_dir)

    def get_configuration(self, filename=None):
        """Fetch the configuration of corresponding to the given filename.

        The returned object is an ordered dict of <section_name: list> where
        each item in the list is an ordered dict of <key: value>.

        It the filename is ommited, it fetches the current configuration.
        """
        if filename is None:
            filename = self.current_config
        return self.proxy.get_config(self.config_dir, filename)

    def run_checks(self):
        """Make sure the configuration corresponds to a mercury.

        - One and only one detector (hardware controller)
        - One and only one acquisition module
        - One and only one detector channel (a.k.a as element)
        - By convention, the channel is numbered 0.
        """
        detectors = self.proxy.get_detectors()
        assert len(detectors) == 1
        modules = self.proxy.get_modules()
        assert len(modules) == 1
        channels = self.proxy.get_channels()
        assert len(channels) == 1
        assert channels == (0,)
        grouped_channels = self.proxy.get_grouped_channels()
        assert grouped_channels == ((0, ), )

    @property
    def connected(self):
        return bool(self.current_config)

    # Acquisition

    def prepare_acquisition(self):
        pass

    def start_acquisition(self):
        self.proxy.start_run(0)

    def stop_acquisition(self):
        self.proxy.stop_run(0)

    def get_acquisition_status(self):
        return ""

    def get_acquisition_data(self):
        return [self.proxy.get_run_data(0)]

    # Infos

    def get_detector_brand(self):
        return Brand.XIA

    def get_detector_type(self):
        return DetectorType.MERCURY

    def get_element_count(self):
        return 1
