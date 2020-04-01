"""Testing positioners widget."""

import pytest

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets.positioners_widget import PositionersWidget
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model


@pytest.mark.usefixtures("local_flint")
class TestPositionersWidget(TestCaseQt):
    def create_scan_info(self, final=False):
        scan_info = {
            "positioners": {
                "positioners_start": {"slit_bottom": 1.0, "slit_top": -1.0},
                "positioners_end": {"slit_bottom": 2.0, "slit_top": -2.0},
                "positioners_dial_start": {"slit_bottom": 3.0, "slit_top": -3.0},
                "positioners_dial_end": {"slit_bottom": 4.0},
                "positioners_units": {
                    "slit_bottom": "mm",
                    "slit_top": None,
                    "slit_foo": None,
                },
            }
        }
        if not final:
            scan_info["positioners"].pop("positioners_end")
            scan_info["positioners"].pop("positioners_dial_end")
        return scan_info

    def create_scan(self,):
        scan = scan_model.Scan()
        scan_info = self.create_scan_info(False)
        scan.setScanInfo(scan_info)
        scan.seal()
        return scan

    def create_flint_model(self):
        flint = flint_model.FlintState()
        return flint

    def test_display_nothing(self):
        # Create a plot with already existing data
        flint = self.create_flint_model()

        widget = PositionersWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)

        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()

    def test_processing_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        flint = self.create_flint_model()

        widget = PositionersWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        scan._setState(scan_model.ScanState.PROCESSING)

        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()

    def test_processed_data(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        flint = self.create_flint_model()

        widget = PositionersWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        scan._setState(scan_model.ScanState.PROCESSING)

        widget.show()
        self.qWaitForWindowExposed(widget)
        finalScanInfo = self.create_scan_info(final=True)
        scan._setFinalScanInfo(finalScanInfo)
        scan._setState(scan_model.ScanState.FINISHED)
        self.qWait(100)
        widget.close()
