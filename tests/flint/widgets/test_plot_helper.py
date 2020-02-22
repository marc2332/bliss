"""Testing plot_helper module."""

import typing

from bliss.flint.widgets import plot_helper
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
