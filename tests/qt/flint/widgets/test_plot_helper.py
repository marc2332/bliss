"""Testing plot_helper module."""

import typing
import pickle

from bliss.flint.widgets.utils import plot_helper
from bliss.flint.model import scan_model


class Args(typing.NamedTuple):
    args: typing.Tuple
    kwargs: typing.Dict


def test_plot_event_aggregator():
    aggregator = plot_helper.PlotEventAggregator()
    scan = scan_model.Scan()
    device = scan_model.Device(scan)
    channel = scan_model.Channel(device)
    scan.seal()

    events = []

    def callback(*args, **kwargs):
        events.append(Args(args, kwargs))

    call = aggregator.callbackTo(callback)
    call(scan_model.ScanDataUpdateEvent(scan, channel=channel))
    call(scan_model.ScanDataUpdateEvent(scan, channel=channel))
    call(scan_model.ScanDataUpdateEvent(scan))
    call(scan_model.ScanDataUpdateEvent(scan, channel=channel))
    aggregator.flush()

    assert len(events) == 2
    assert events[0].args[0].selectedChannel() is None
    assert events[1].args[0].selectedChannel() is channel


def test_scalar_event_aggregator__channels():
    aggregator = plot_helper.ScalarEventAggregator()
    scan = scan_model.Scan()
    device = scan_model.Device(scan)
    channel1 = scan_model.Channel(device)
    channel1.setName("channel1")
    channel2 = scan_model.Channel(device)
    channel2.setName("channel2")
    channel3 = scan_model.Channel(device)
    channel3.setName("channel3")
    scan.seal()

    events = []

    def callback(*args, **kwargs):
        events.append(Args(args, kwargs))

    call = aggregator.callbackTo(callback)
    call(scan_model.ScanDataUpdateEvent(scan, channels=[channel1, channel2]))
    call(scan_model.ScanDataUpdateEvent(scan, channels=[channel1, channel2]))
    call(scan_model.ScanDataUpdateEvent(scan, channel=channel3))
    call(scan_model.ScanDataUpdateEvent(scan, channels=[channel1, channel2]))
    aggregator.flush()

    assert len(events) == 2
    assert events[0].args[0].isUpdatedChannelName("channel3")
    assert events[1].args[0].isUpdatedChannelName("channel1")
    assert events[1].args[0].isUpdatedChannelName("channel1")


def test_scalar_event_aggregator__devices():
    aggregator = plot_helper.ScalarEventAggregator()
    scan = scan_model.Scan()
    device1 = scan_model.Device(scan)
    device2 = scan_model.Device(scan)
    scan.seal()

    events = []

    def callback(*args, **kwargs):
        events.append(Args(args, kwargs))

    call = aggregator.callbackTo(callback)
    call(scan_model.ScanDataUpdateEvent(scan, masterDevice=device1))
    call(scan_model.ScanDataUpdateEvent(scan, masterDevice=device2))
    call(scan_model.ScanDataUpdateEvent(scan, masterDevice=device1))
    call(scan_model.ScanDataUpdateEvent(scan, masterDevice=device2))
    call(scan_model.ScanDataUpdateEvent(scan, masterDevice=device2))
    aggregator.flush()

    assert len(events) == 2
    assert events[0].args[0].selectedDevice() is device1
    assert events[1].args[0].selectedDevice() is device2


def test_persistence():
    data = plot_helper.PlotConfiguration()
    data.interaction_mode = "pan"
    result = pickle.loads(pickle.dumps(data))
    assert result.interaction_mode == "pan"
