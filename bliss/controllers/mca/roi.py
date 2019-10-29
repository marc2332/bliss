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
        if not self.nrois:
            return "NO ROI defined yet !!"

        roi_table = []
        header = ("Name", "start", "end")

        for (roi_name, values) in self.items():
            start, end = values
            roi_line = (f"{roi_name}", f"{start}", f"{end}")
            roi_table.append(roi_line)

        return tabulate(tuple(roi_table), header, numalign="right", tablefmt="simple")

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

    @property
    def nrois(self):
        return len(self.config)

    # Public methods

    def get_names(self):
        """Return names of all configured ROIs.
        """
        return list(self.config.keys())

    def get(self, roi_name):
        """Return ROI object from its name.
        <roi_name> ('str'): name of a ROI
        """
        return literal_eval(self.config[roi_name])

    def set(self, name, start, end):
        """Add a ROI named <name> defined by low channel index <start> and high
        channel index <end>.
        """
        # Check
        self.config[name] = start, end

    def remove(self, name):
        """Remove ROI named <roi>.
        """
        del self.config[name]

    def clear(self):
        """Remove all ROIs from config setting.
        """
        self.config.clear()

    def __len__(self):
        return len(self.config)

    def __contains__(self, name):
        return name in self.config

    def keys(self):
        return list(self.config.keys())

    def values(self):
        return [literal_eval(value) for value in self.config.values()]

    def items(self):
        return [(name, literal_eval(value)) for (name, value) in self.config.items()]

    def has_key(self, name):
        return self.config.has_key(name)

    def update(self, rois):
        for name, roi in rois.items():
            self.config[name] = roi
