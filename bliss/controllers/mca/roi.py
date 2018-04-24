"""Provide an access to the MCA ROI configuration."""

from ast import literal_eval

from bliss.config.settings import HashSetting


class RoiConfig(object):

    def __init__(self, mca):
        self._mca = mca
        self._name = mca.name
        self._setting = None

    # Properties

    @property
    def mca(self):
        return self._mca

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        if self._setting is None:
            name = self.name + '_roi_config'
            self._setting = HashSetting(name)
        return self._setting

    # Public methods

    def get_names(self):
        return self.config.keys()

    def add_roi(self, name, center, left, right):
        # Check
        self._resolve(center, left, right)
        self.config[name] = center, left, right

    def remove_roi(self, name):
        del self.config[name]

    def clear(self):
        self.config.clear()

    def resolve(self, name):
        center, left, right = literal_eval(self.config[name])
        return self._resolve(center, left, right)

    # Solving logic

    def _resolve(self, center, left, right):
        return int(center-left), int(center - right)
