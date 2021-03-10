"""Testing for profile action"""

from bliss.flint.widgets.utils import profile_action
from bliss.flint.widgets.utils import plot_helper
from silx.gui.plot.tools.profile import rois


state_rois_v1_7 = b"\x80\x03]q\x00csilx.gui.plot.tools.profile.rois\nProfileScatterCrossROI\nq\x01X\x07\x00\x00\x00Profileq\x02K\nK\n\x86q\x03\x87q\x04a."

rois_v1_7 = (state_rois_v1_7, [(rois.ProfileScatterCrossROI, (10, 10))])


def test_read_stored_state_bliss_1_7(local_flint):
    plot = plot_helper.FlintPlot()
    action = profile_action.ProfileAction(plot, None, "image")
    state, expectedRois = rois_v1_7
    action.restoreState(state)

    m = action.manager()
    roiManager = m.getRoiManager()

    result = [
        (type(r), action.getGeometry(r))
        for r in roiManager.getRois()
        if r.getFocusProxy() is None
    ]
    print(result)
    assert result == expectedRois
