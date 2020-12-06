"""Testing the remote API provided by Flint."""

import logging
import pickle

from bliss.controllers.lima import roi as lima_roi

logger = logging.getLogger(__name__)


def test_used_object():
    """Make sure object shared in the RPC are still picklable"""
    roi = lima_roi.ArcRoi(0, 1, 2, 3, 4, 5, 6)
    pickle.loads(pickle.dumps(roi))
    roi = lima_roi.Roi(0, 1, 2, 3)
    pickle.loads(pickle.dumps(roi))
    roi = lima_roi.RoiProfile(0, 1, 2, 3, mode="vertical")
    pickle.loads(pickle.dumps(roi))
