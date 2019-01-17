from .diff_base import (
    Diffractometer,
    get_current_diffractometer,
    set_current_diffractometer,
    get_diffractometer_list,
    pprint_diff_settings,
    remove_diff_settings,
)
from .diff_fourc import DiffE4CH, DiffE4CV

__CLASS_DIFF = {"E4CH": DiffE4CH, "E4CV": DiffE4CV}


def get_diffractometer_class(geometry_name):
    klass = __CLASS_DIFF.get(geometry_name, Diffractometer)
    return klass
