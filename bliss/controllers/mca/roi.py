"""Provide an access to the MCA ROI configuration."""

from ast import literal_eval
from tabulate import tabulate

from bliss.config.settings import HashSetting


class RoiConfig:
    """Represent the configuration a Region Of Interest that user can define to
    sum events included between low and high channel boundaries.
    """

    def __init__(self, mca):
        self._mca = mca
        self._name = mca.name
        self._setting = None

    def __info__(self):
        """For BLISS shell typing helper information.
        """
        roi_table = []
        header = ("Name", "start", "end")
        separator = ("------", "-----", "-----")
        roi_table.append(header)
        roi_table.append(separator)

        for roi_name in self.get_names():
            start, end = self.get_roi(roi_name)
            roi_line = (f"{roi_name}", f"{start}", f"{end}")
            roi_table.append(roi_line)

        return tabulate(tuple(roi_table), numalign="right", tablefmt="plain")

    # Properties

    @property
    def mca(self):
        """Return MCA device of this ROI config.
        """
        return self._mca

    @property
    def name(self):
        """Return name of the ROI.
        """
        return self._name

    @property
    def config(self):
        """Return setting corresponding to the ROI configuration.
        Create it if not yet present.
        """
        if self._setting is None:
            name = self.name + "_roi_config"
            self._setting = HashSetting(name)
        return self._setting

    # Public methods

    def get_names(self):
        """Return names of all configured ROIs.
        """
        return list(self.config.keys())

    def get_roi(self, roi_name):
        """Return ROI object from its name.
        <roi_name> ('str'): name of a ROI
        """
        return literal_eval(self.config[roi_name])

    def add_roi(self, name, start, end):
        """Add a ROI named <name> defined by low channel index <start> and high
        channel index <end>.
        """
        # Check
        self.config[name] = start, end

    def remove_roi(self, name):
        """Remove ROI named <roi>.
        """
        del self.config[name]

    def clear(self):
        """Remove all ROIs from config setting.
        """
        self.config.clear()
