"""Provide an access to the MCA ROI configuration."""

from ast import literal_eval

from bliss.config.settings import HashSetting


class RoiConfig(object):
    def __init__(self, mca):
        self._mca = mca
        self._name = mca.name
        self._setting = None

    # Properties

    def __repr__(self):

        template = "{:<10} {:>8} {:>8} {:>8} {:>8} {:>8}\n"

        roi_listing = template.format(
            "Name", "(center", "left", "right)", "(start", "stop)"
        )
        roi_listing += "-" * 10 + (" " + "-" * 8) * 5 + "\n"

        for roi_name in self.get_names():
            center, left, right = self.get_roi(roi_name)
            start, stop = self._resolve(center, left, right)
            roi_listing += template.format(roi_name, center, left, right, start, stop)

        return roi_listing

    @property
    def mca(self):
        return self._mca

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        if self._setting is None:
            name = self.name + "_roi_config"
            self._setting = HashSetting(name)
        return self._setting

    # Public methods

    def get_names(self):
        """
        Returns names of all configured ROIs.
        """
        return list(self.config.keys())

    def get_roi(self, roi_name):
        return literal_eval(self.config[roi_name])

    def add_roi(self, name, center, left, right):
        # Check
        self._resolve(center, left, right)
        self.config[name] = center, left, right

    def remove_roi(self, name):
        del self.config[name]

    def clear(self):
        self.config.clear()

    def resolve(self, name):
        """
        Returns start stop indexes for the given ROI name.
        """
        center, left, right = literal_eval(self.config[name])
        return self._resolve(center, left, right)

    # Solving logic
    def _resolve(self, center, left, right):
        """
        Returns start stop indexes for the given (c,l,r) energies(indexes for now).
        """
        return int(center - left), int(center + right)
