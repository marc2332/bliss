"""Testing LogWidget."""

import pytest

from bliss.flint.helper import model_helper
from bliss.flint.model import scan_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model


def test_clone_channel_ref():
    source = plot_model.Plot()
    destination = plot_model.Plot()
    channel = plot_model.ChannelRef(source, "foo")
    cloned = model_helper.cloneChannelRef(destination, channel)
    assert channel is not cloned
    assert channel == cloned
    assert cloned.parent() is destination


def test_clone_none_channel_ref():
    destination = plot_model.Plot()
    channel = None
    cloned = model_helper.cloneChannelRef(destination, channel)
    assert cloned is None


def test_reach_any_curve_item_from_device__empty_plot():
    plot = plot_model.Plot()
    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    scan.seal()

    item = model_helper.reachAnyCurveItemFromDevice(plot, scan, master)
    assert item is None


def test_reach_any_curve_item_from_device__with_xy():
    plot = plot_model.Plot()
    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    channel1 = scan_model.Channel(master)
    channel1.setName("c1")
    channel2 = scan_model.Channel(master)
    channel2.setName("c2")
    scan.seal()

    found = model_helper.reachAnyCurveItemFromDevice(plot, scan, master)
    assert found is item


def test_reach_any_curve_item_from_device__only_x():
    plot = plot_model.Plot()
    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    channel1 = scan_model.Channel(master)
    channel1.setName("c1")
    channel2 = scan_model.Channel(master)
    channel2.setName("c2")
    scan.seal()

    found = model_helper.reachAnyCurveItemFromDevice(plot, scan, master)
    assert found is item


def test_reach_any_curve_item_from_device__with_others():
    plot = plot_model.Plot()
    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o1")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o2")
    other.setYChannel(channel)

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o3")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o4")
    other.setYChannel(channel)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    channel1 = scan_model.Channel(master)
    channel1.setName("c1")
    channel2 = scan_model.Channel(master)
    channel2.setName("c2")
    scan.seal()

    found = model_helper.reachAnyCurveItemFromDevice(plot, scan, master)
    assert found is item


def test_reach_any_curve_item_from_device__sub_device():
    plot = plot_model.Plot()
    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o1")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o2")
    other.setYChannel(channel)

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o3")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o4")
    other.setYChannel(channel)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    scan.seal()

    found = model_helper.reachAnyCurveItemFromDevice(plot, scan, master)
    assert found is item


def test_reach_all_curve_item_from_device__with_others():
    plot = plot_model.Plot()
    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o1")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o2")
    other.setYChannel(channel)

    item1 = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item1.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item1.setYChannel(channel)
    plot.addItem(item1)

    item2 = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item2.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c3")
    item2.setYChannel(channel)
    plot.addItem(item2)

    other = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "o3")
    other.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o4")
    other.setYChannel(channel)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    other_master = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(device)
    channel2.setName("c3")
    channel2 = scan_model.Channel(other_master)
    channel2.setName("o1")
    channel2 = scan_model.Channel(other_master)
    channel2.setName("o2")
    channel2 = scan_model.Channel(other_master)
    channel2.setName("o3")
    scan.seal()

    founds = model_helper.reachAllCurveItemFromDevice(plot, scan, master)
    assert set(founds) == set([item1, item2])


def test_consistent_top_master__from_device():
    plot = plot_model.Plot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(master2)
    channel2.setName("o1")
    scan.seal()

    found = model_helper.getConsistentTopMaster(scan, item)
    assert found is master


def test_consistent_top_master__only_x():
    plot = plot_model.Plot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(master2)
    channel2.setName("o1")
    scan.seal()

    found = model_helper.getConsistentTopMaster(scan, item)
    assert found is master


def test_consistent_top_master__only_y():
    plot = plot_model.Plot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(master2)
    channel2.setName("o1")
    scan.seal()

    found = model_helper.getConsistentTopMaster(scan, item)
    assert found is master


def test_consistent_top_master__not_consistent():
    plot = plot_model.Plot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "o1")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(master2)
    channel2.setName("o1")
    scan.seal()

    found = model_helper.getConsistentTopMaster(scan, item)
    assert found is None


def test_consistent_top_master__not_available_channel():
    plot = plot_model.Plot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "z1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    device = scan_model.Device(scan)
    device.setMaster(master)
    channel1 = scan_model.Channel(device)
    channel1.setName("c1")
    channel2 = scan_model.Channel(device)
    channel2.setName("c2")
    channel2 = scan_model.Channel(master2)
    channel2.setName("o1")
    scan.seal()

    found = model_helper.getConsistentTopMaster(scan, item)
    assert found is None


def test_most_used_xchannel_per_masters():
    plot = plot_item_model.CurvePlot()

    for channel_name in ["c1", "c2", "c1", "c3", "c3", "c3"]:
        item = plot_item_model.CurveItem(plot)
        channel = plot_model.ChannelRef(plot, channel_name)
        item.setXChannel(channel)
        plot.addItem(item)

    scan = scan_model.Scan()
    master1 = scan_model.Device(scan)
    master2 = scan_model.Device(scan)
    channel1 = scan_model.Channel(master1)
    channel1.setName("c1")
    channel2 = scan_model.Channel(master1)
    channel2.setName("c2")
    channel3 = scan_model.Channel(master2)
    channel3.setName("c3")
    scan.seal()

    result = model_helper.getMostUsedXChannelPerMasters(scan, plot)
    assert result == {master1: channel1.name(), master2: channel3.name()}


def test_remove_item_and_keep_axes__scatter():
    plot = plot_item_model.ScatterPlot()

    item = plot_item_model.ScatterItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    channel = plot_model.ChannelRef(plot, "c3")
    item.setValueChannel(channel)
    plot.addItem(item)

    model_helper.removeItemAndKeepAxes(plot, item)
    new_items = list(plot.items())
    assert len(new_items) == 1
    new_item = new_items[0]
    assert new_item is not item
    assert new_item.xChannel() == item.xChannel()
    assert new_item.yChannel() == item.yChannel()
    assert new_item.valueChannel() is None


def test_remove_item_and_keep_axes__curve():
    plot = plot_item_model.CurvePlot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    model_helper.removeItemAndKeepAxes(plot, item)
    new_items = list(plot.items())
    assert len(new_items) == 1
    new_item = new_items[0]
    assert new_item is not item
    assert new_item.xChannel() == item.xChannel()
    assert new_item.yChannel() is None


def test_remove_item_and_keep_axes__other():
    plot = plot_item_model.McaPlot()

    item = plot_item_model.McaItem(plot)
    plot.addItem(item)

    model_helper.removeItemAndKeepAxes(plot, item)
    new_items = list(plot.items())
    assert len(new_items) == 0


def test_create_scatter_item__empty():
    plot = plot_item_model.ScatterPlot()

    scan = scan_model.Scan()
    master1 = scan_model.Device(scan)
    channel1 = scan_model.Channel(master1)
    channel1.setName("c1")
    scan.seal()

    model_helper.createScatterItem(plot, channel1)
    new_items = list(plot.items())
    assert len(new_items) == 1
    new_item = new_items[0]
    assert new_item.xChannel() is None
    assert new_item.yChannel() is None
    assert new_item.valueChannel().name() == channel1.name()


def test_create_scatter_item__existing_axes():
    plot = plot_item_model.ScatterPlot()

    item = plot_item_model.ScatterItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    channel = plot_model.ChannelRef(plot, "c3")
    item.setValueChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master1 = scan_model.Device(scan)
    channel1 = scan_model.Channel(master1)
    channel1.setName("n1")
    scan.seal()

    model_helper.createScatterItem(plot, channel1)
    new_items = list(plot.items())
    assert len(new_items) == 2
    new_item = new_items[1]
    assert new_item.xChannel().name() == item.xChannel().name()
    assert new_item.yChannel().name() == item.yChannel().name()
    assert new_item.valueChannel().name() == channel1.name()


def test_create_curve_item__empty():
    plot = plot_item_model.CurvePlot()

    scan = scan_model.Scan()
    master1 = scan_model.Device(scan)
    channel1 = scan_model.Channel(master1)
    channel1.setName("c1")
    scan.seal()

    model_helper.createCurveItem(plot, channel1, "left")
    new_items = list(plot.items())
    assert len(new_items) == 1
    new_item = new_items[0]
    assert new_item.yAxis() == "left"
    # INFO: There is a magic behavior to select a default axis
    # assert new_item.xChannel() is None
    assert new_item.yChannel().name() == channel1.name()


def test_create_curve_item__existing_axes():
    plot = plot_item_model.CurvePlot()

    item = plot_item_model.CurveItem(plot)
    channel = plot_model.ChannelRef(plot, "c1")
    item.setXChannel(channel)
    channel = plot_model.ChannelRef(plot, "c2")
    item.setYChannel(channel)
    plot.addItem(item)

    scan = scan_model.Scan()
    master1 = scan_model.Device(scan)
    channel1 = scan_model.Channel(master1)
    channel1.setName("n1")
    channel2 = scan_model.Channel(master1)
    channel2.setName("c1")
    scan.seal()

    model_helper.createCurveItem(plot, channel1, "left")
    new_items = list(plot.items())
    assert len(new_items) == 2
    new_item = new_items[1]
    assert new_item.yAxis() == "left"
    assert new_item.xChannel().name() == item.xChannel().name()
    assert new_item.yChannel().name() == channel1.name()
