"""Testing ct widget."""

import pytest
import numpy

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets.ct_widget import CtWidget
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model


@pytest.mark.usefixtures("local_flint")
class TestCtWidget(TestCaseQt):
    def create_scan(self):
        scan = scan_model.Scan()
        master = scan_model.Device(scan)
        master.setName("master")
        device = scan_model.Device(scan)
        device.setName("device")
        device.setMaster(master)
        channel = scan_model.Channel(device)
        channel.setName("chan1")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan2")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan3")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan4")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan5")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan6")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan-spectrum")
        channel.setType(scan_model.ChannelType.SPECTRUM)

        scan_info = {}
        scan_info["count_time"] = 1
        scan.setScanInfo(scan_info)
        scan.seal()
        return scan

    def create_flint_model(self):
        flint = flint_model.FlintState()
        return flint

    def test_display_nothing(self):
        # Create a plot with already existing data
        flint = self.create_flint_model()

        widget = CtWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)

        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()

    def test_processing_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        flint = self.create_flint_model()

        widget = CtWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)

        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()

    def test_processed_data(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        flint = self.create_flint_model()

        array = numpy.array([10])
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        array = numpy.array(["foo"])
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan2").setData(data)
        array = numpy.array([10.01])
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan3").setData(data)
        array = numpy.array([10, 20])
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan4").setData(data)
        array = numpy.array([])
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan5").setData(data)

        widget = CtWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        scan._setState(scan_model.ScanState.FINISHED)
        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()
