"""Testing for profile action"""

import numpy
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
    assert result == expectedRois


def test_read_write_profiles(local_flint):
    plot = plot_helper.FlintPlot()
    action = profile_action.ProfileAction(plot, None, "image")

    m = action.manager()
    roiManager = m.getRoiManager()

    r = rois.ProfileImageLineROI()
    r.setEndPoints((10, 10), (20, 20))
    roiManager.addRoi(r)
    r = rois.ProfileImageCrossROI()
    r.setPosition((10, 10))
    roiManager.addRoi(r)

    r = rois.ProfileScatterLineROI()
    r.setEndPoints((10, 10), (20, 20))
    roiManager.addRoi(r)
    r = rois.ProfileScatterCrossROI()
    r.setPosition((10, 10))
    roiManager.addRoi(r)

    state = action.saveState()

    plot2 = plot_helper.FlintPlot()
    action2 = profile_action.ProfileAction(plot2, None, "image")
    action2.restoreState(state)
    state2 = action2.saveState()
    assert state == state2


def test_profile_centering_image_line():
    plot = plot_helper.FlintPlot()
    action = profile_action.ProfileAction(plot, None, "image")

    image = numpy.arange(100 * 100)
    image.shape = 100, 100
    plot.addImage(image)

    p = rois.ProfileImageLineROI()
    action.manager().getRoiManager().centerRoi(p)
    p1, p2 = p.getEndPoints()
    numpy.testing.assert_array_equal((p1 + p2) * 0.5, (50.0, 50.0))


def test_profile_centering_image_cross():
    plot = plot_helper.FlintPlot()
    action = profile_action.ProfileAction(plot, None, "image")

    image = numpy.arange(100 * 100)
    image.shape = 100, 100
    plot.addImage(image)

    p = rois.ProfileImageCrossROI()
    action.manager().getRoiManager().centerRoi(p)
    p = p.getPosition()
    numpy.testing.assert_array_equal(p, (50.0, 50.0))


def test_profile_centering_scatter_cross():
    plot = plot_helper.FlintPlot()
    action = profile_action.ProfileAction(plot, None, "image")

    x = numpy.arange(101)
    y = numpy.arange(101)
    v = numpy.arange(101)
    plot.addScatter(x, y, v)

    p = rois.ProfileScatterCrossROI()
    action.manager().getRoiManager().centerRoi(p)
    p = p.getPosition()
    numpy.testing.assert_array_equal(p, (50.0, 50.0))
