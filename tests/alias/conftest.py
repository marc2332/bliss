import pytest
from bliss.common.tango import DeviceProxy
from bliss.controllers.lima.roi import Roi


@pytest.fixture
def alias_session(beacon, lima_simulator):
    session = beacon.get("test_alias")
    env_dict = dict()
    session.setup(env_dict)

    ls = env_dict["lima_simulator"]
    rois = ls.roi_counters
    dev_name = lima_simulator[0].lower()
    roi_dev = DeviceProxy(dev_name.replace("limaccds", "roicounter"))
    r1 = Roi(0, 0, 100, 200)
    rois["r1"] = r1
    r2 = Roi(100, 100, 100, 200)
    rois["r2"] = r2
    r3 = Roi(200, 200, 200, 200)
    rois["r3"] = r3

    env_dict["ALIASES"].create_alias("myroi3", "lima_simulator.roi_counters.r3.sum")

    yield env_dict, session
    session.close()
