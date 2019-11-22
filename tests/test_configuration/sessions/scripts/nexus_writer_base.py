from bliss.controllers.lima.roi import Roi as LimaRoi
from bliss.controllers.lima.lima_base import Lima
from bliss.controllers.mca.base import BaseMCA
from bliss.common.session import get_current_session

# Not required but useful for manual testing:
from nexus_writer_service.session_api import *


def objects_of_type(*classes):
    ret = {}
    session = get_current_session()
    for name in session.object_names:
        try:
            obj = session.env_dict[name]
        except KeyError:
            continue
        if isinstance(obj, classes):
            ret[name] = obj
    return ret


# Add lima ROI's
rois = {
    "roi1": LimaRoi(0, 0, 100, 200),
    "roi2": LimaRoi(10, 20, 200, 500),
    "roi3": LimaRoi(20, 60, 500, 500),
    "roi4": LimaRoi(60, 20, 50, 10),
}
for lima in objects_of_type(Lima).values():
    lima.roi_counters.update(rois)


# Add mca ROI's
rois = {"roi1": (500, 550), "roi2": (600, 650), "roi3": (700, 750)}
for mca in objects_of_type(BaseMCA).values():
    for name, roi in rois.items():
        mca.rois.set(name, *roi)
