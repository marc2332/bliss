# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Helper functions to deal with Flint models
"""

from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple

from silx.gui import colors

from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.model import style_model


def reachAnyCurveItemFromDevice(
    plot: plot_model.Plot, scan: scan_model.Scan, topMaster: scan_model.Device
) -> Optional[plot_item_model.CurveItem]:
    """
    Reach any plot item from this top master
    """
    for item in plot.items():
        if not isinstance(item, plot_item_model.CurveItem):
            continue
        itemChannel = item.xChannel()
        if itemChannel is None:
            itemChannel = item.yChannel()
        assert itemChannel is not None
        channelName = itemChannel.name()
        channel = scan.getChannelByName(channelName)
        if channel is None:
            continue
        itemMaster = channel.device().topMaster()
        if itemMaster is topMaster:
            return item
    return None


def reachAllCurveItemFromDevice(
    plot: plot_model.Plot, scan: scan_model.Scan, topMaster: scan_model.Device
) -> List[plot_item_model.CurveItem]:
    """
    Reach all plot items from this top master
    """
    curves = []
    for item in plot.items():
        if not isinstance(item, plot_item_model.CurveItem):
            continue
        itemChannel = item.xChannel()
        if itemChannel is None:
            itemChannel = item.yChannel()
        assert itemChannel is not None
        channelName = itemChannel.name()
        channel = scan.getChannelByName(channelName)
        assert channel is not None
        itemMaster = channel.device().topMaster()
        if itemMaster is topMaster:
            curves.append(item)
    return curves


def getConsistentTopMaster(
    scan: scan_model.Scan, plotItem: plot_item_model.CurveItem
) -> Optional[scan_model.Device]:
    """Returns a top master from this item only if channels comes from the
    same top master.

    If there is a single top master (x-channel or y-channel is missing), this
    top master is returned.
    """
    xChannel = plotItem.xChannel()
    yChannel = plotItem.yChannel()
    if xChannel is None and yChannel is None:
        return None

    if xChannel is None or yChannel is None:
        # One or the other is valid
        channelRef = xChannel if xChannel is not None else yChannel
        # With one or the other the master channel is valid
        name = channelRef.name()
        channel = scan.getChannelByName(name)
        if channel is None:
            return None
        return channel.device().topMaster()

    x = xChannel.name()
    channelX = scan.getChannelByName(x)
    if channelX is None:
        return None

    y = yChannel.name()
    channelY = scan.getChannelByName(y)
    if channelY is None:
        return None

    topMasterX = channelX.device().topMaster()
    topMasterY = channelY.device().topMaster()
    if topMasterX is not topMasterY:
        return None
    return topMasterX


def getMostUsedXChannelPerMasters(
    scan: scan_model.Scan, plotModel: plot_item_model.CurvePlot
) -> Dict[scan_model.Device, str]:
    """
    Returns a dictionary mapping top master with the most used x-channels.
    """
    if scan is None:
        return {}
    if plotModel is None:
        return {}

    # Count the amount of same x-channel per top masters
    xChannelsPerMaster: Dict[scan_model.Device, Dict[str, int]] = {}
    for plotItem in plotModel.items():
        if not isinstance(plotItem, plot_item_model.CurveItem):
            continue
        # Here is only top level curve items
        xChannel = plotItem.xChannel()
        if xChannel is None:
            continue
        xChannelName = xChannel.name()
        channel = scan.getChannelByName(xChannelName)
        if channel is not None:
            topMaster = channel.device().topMaster()
            if topMaster not in xChannelsPerMaster:
                counts: Dict[str, int] = {}
                xChannelsPerMaster[topMaster] = counts
            else:
                counts = xChannelsPerMaster[topMaster]

            counts[xChannelName] = counts.get(xChannelName, 0) + 1

    # Returns the most used channels
    xChannelPerMaster = {}
    for master, counts in xChannelsPerMaster.items():
        channels = sorted(counts.keys(), key=lambda x: counts[x], reverse=True)
        most_often_used_channel = channels[0]
        xChannelPerMaster[master] = most_often_used_channel

    return xChannelPerMaster


def cloneChannelRef(
    plot: plot_model.Plot, channel: Optional[plot_model.ChannelRef]
) -> Optional[plot_model.ChannelRef]:
    if channel is None:
        return None
    name = channel.name()
    cloned = plot_model.ChannelRef(parent=plot, channelName=name)
    return cloned


def removeItemAndKeepAxes(plot: plot_model.Plot, item: plot_model.Item):
    """
    Remove an item from the model and keep the axes, if available.

    If the item is the last one, create a new item to keep the available axes.

    Only CurveItem and ScatterItem provides axes. For other ones the item is
    just removed.
    """
    if isinstance(item, plot_item_model.ScatterItem):
        scatters = []
        for scatter in plot.items():
            if isinstance(scatter, plot_item_model.ScatterItem):
                scatters.append(scatter)

        if len(scatters) == 1:
            # Only remove the value to remember the axes
            newItem = plot_item_model.ScatterItem(plot)
            xChannel = cloneChannelRef(plot, item.xChannel())
            yChannel = cloneChannelRef(plot, item.yChannel())
            if xChannel is None and yChannel is None:
                # It does not contain x or y-axis to keep
                plot.removeItem(item)
            else:
                if xChannel is not None:
                    newItem.setXChannel(xChannel)
                if yChannel is not None:
                    newItem.setYChannel(yChannel)
                with plot.transaction():
                    plot.removeItem(item)
                    plot.addItem(newItem)
        else:
            # It's not the last one
            plot.removeItem(item)
    elif isinstance(item, plot_item_model.CurveItem):
        xChannel = item.xChannel()
        if xChannel is not None:
            # Reach curves sharing the same x-channel
            curves = []
            for curve in plot.items():
                if isinstance(curve, plot_item_model.CurveItem):
                    if xChannel == curve.xChannel():
                        curves.append(curve)

            if len(curves) == 1:
                # Only remove the value to remember the axes
                xChannel = cloneChannelRef(plot, xChannel)
                newItem = plot_item_model.CurveItem(plot)
                newItem.setXChannel(xChannel)
                with plot.transaction():
                    plot.removeItem(item)
                    plot.addItem(newItem)
            else:
                # It's not the last one
                plot.removeItem(item)
        else:
            # It does not contain x-axis to keep
            plot.removeItem(item)
    else:
        # It's something else than curve or scatter
        plot.removeItem(item)


def createScatterItem(
    plot: plot_model.Plot, channel: scan_model.Channel
) -> Tuple[plot_model.Item, bool]:
    """
    Create an item to a plot using a channel.

    Returns a tuple containing the created or updated item, plus a boolean to know if the item was updated.
    """
    channel_name = channel.name()

    # Reach any plot item from this master
    baseItem: Optional[plot_item_model.ScatterItem]
    for baseItem in plot.items():
        if isinstance(baseItem, plot_item_model.ScatterItem):
            break
    else:
        baseItem = None

    if baseItem is not None:
        isAxis = baseItem.valueChannel() is None
        if isAxis:
            baseItem.setValueChannel(plot_model.ChannelRef(plot, channel_name))
            # It's now an item with a value
            return baseItem, True
        else:
            # Create a new item using axis from baseItem
            xChannel = cloneChannelRef(plot, baseItem.xChannel())
            yChannel = cloneChannelRef(plot, baseItem.yChannel())
            newItem = plot_item_model.ScatterItem(plot)
            if xChannel is not None:
                newItem.setXChannel(xChannel)
            if yChannel is not None:
                newItem.setYChannel(yChannel)
            newItem.setValueChannel(plot_model.ChannelRef(plot, channel_name))
    else:
        # No axes are specified
        # FIXME: Maybe we could use scan infos to reach the default axes
        newItem = plot_item_model.ScatterItem(plot)
        newItem.setValueChannel(plot_model.ChannelRef(plot, channel_name))
    plot.addItem(newItem)
    return newItem, False


def createCurveItem(
    plot: plot_model.Plot, channel: scan_model.Channel, yAxis: str
) -> Tuple[plot_model.Item, bool]:
    """
    Create an item to a plot using a channel.

    Returns a tuple containing the created or updated item, plus a boolean to know if the item was updated.
    """
    # Reach the master device
    topMaster = channel.device().topMaster()
    scan = topMaster.scan()

    # Reach any plot item from this master
    item = reachAnyCurveItemFromDevice(plot, scan, topMaster)

    if item is not None:
        isAxis = item.yChannel() is None
        if isAxis:
            item.setYChannel(plot_model.ChannelRef(plot, channel.name()))
            item.setYAxis(yAxis)
            return item, True
        else:
            xChannel = cloneChannelRef(plot, item.xChannel())
            newItem = plot_item_model.CurveItem(plot)
            newItem.setXChannel(xChannel)
            newItem.setYChannel(plot_model.ChannelRef(plot, channel.name()))
            newItem.setYAxis(yAxis)
    else:
        # No other x-axis is specified
        # Reach another channel name from the same top master
        channelNames = []
        for device in scan.devices():
            if device.topMaster() is not topMaster:
                continue
            channelNames.extend([c.name() for c in device.channels()])
        channelNames.remove(channel.name())

        if len(channelNames) > 0:
            # Pick the first one
            # FIXME: Maybe we could use scan infos to reach the default channel
            channelName = channelNames[0]
        else:
            # FIXME: Maybe it's better idea to display it with x-index
            channelName = channel.name()

        newItem = plot_item_model.CurveItem(plot)
        newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
        newItem.setYChannel(plot_model.ChannelRef(plot, channel.name()))
        newItem.setYAxis(yAxis)

    plot.addItem(newItem)
    return newItem, False


def filterUsedDataItems(plot, channel_names):
    """Filter plot items according to expected channel names

    Returns a tuple within channels which have items, items which are
    not needed and channel names which have no equivalent items.
    """
    channel_names = set(channel_names)
    used_items = []
    unneeded_items = []
    for item in plot.items():
        if isinstance(item, plot_item_model.ScatterItem):
            channel = item.valueChannel()
        elif isinstance(item, plot_item_model.CurveItem):
            channel = item.yChannel()
        else:
            raise NotImplementedError("Item type %s unsupported" % type(item))
        if channel is not None:
            if channel.name() in channel_names:
                used_items.append(item)
                channel_names.remove(channel.name())
                continue
        unneeded_items.append(item)

    unused_channels = list(channel_names)
    return used_items, unneeded_items, unused_channels


def getChannelNamesDisplayedAsValue(plot: plot_model.Plot) -> List[str]:
    names = []
    for item in plot.items():
        if isinstance(item, plot_item_model.CurveItem):
            channel = item.yChannel()
            if channel is None:
                continue
            names.append(channel.name())
        elif isinstance(item, plot_item_model.McaItem):
            channel = item.mcaChannel()
            if channel is None:
                continue
            names.append(channel.name())
        if isinstance(item, plot_item_model.ScatterItem):
            channel = item.valueChannel()
            if channel is None:
                continue
            names.append(channel.name())
        if isinstance(item, plot_item_model.ImageItem):
            channel = item.imageChannel()
            if channel is None:
                continue
            names.append(channel.name())
    return names


def isChannelUsedAsAxes(plot: plot_model.Plot, channel: scan_model.Channel):
    channel_name = channel.name()
    for item in plot.items():
        if isinstance(item, plot_item_model.CurveItem):
            channel = item.xChannel()
            if channel is None:
                continue
            if channel.name() == channel_name:
                return True
        elif isinstance(item, plot_item_model.ScatterItem):
            channel = item.xChannel()
            if channel is not None:
                if channel.name() == channel_name:
                    return True
            channel = item.yChannel()
            if channel is not None:
                if channel.name() == channel_name:
                    return True

    return False


def isChannelDisplayedAsValue(plot: plot_model.Plot, channel: scan_model.Channel):
    channel_name = channel.name()
    for item in plot.items():
        if isinstance(item, plot_item_model.CurveItem):
            channel = item.yChannel()
            if channel is None:
                continue
            if channel.name() == channel_name:
                return True
        elif isinstance(item, plot_item_model.McaItem):
            channel = item.mcaChannel()
            if channel is None:
                continue
            if channel.name() == channel_name:
                return True
        elif isinstance(item, plot_item_model.ScatterItem):
            channel = item.valueChannel()
            if channel is None:
                continue
            if channel.name() == channel_name:
                return True
        elif isinstance(item, plot_item_model.ImageItem):
            channel = item.imageChannel()
            if channel is None:
                continue
            if channel.name() == channel_name:
                return True

    return False


def getFastChannel(
    channel1: scan_model.Channel, channel2: scan_model.Channel
) -> Optional[scan_model.Channel]:
    """Returns the fast channel from input channels.

    If no one is a fast channel, None is returned
    """
    for channel in [channel1, channel2]:
        m = channel.metadata()
        if m is not None:
            if m.axisKind == scan_model.AxisKind.FAST:
                return channel
    return None


def getColormapFromItem(
    item: plot_model.Item, style: style_model.Style
) -> colors.Colormap:
    """Returns the colormap from an item, taking care of the cache.
    """
    colormap = item.colormap()
    if colormap is None:
        # Store the colormap
        # FIXME as the colormap is exposed to the colormap dialog
        # it have to be synchronized to the item style
        colormap = colors.Colormap(style.colormapLut)
        item.setColormap(colormap)
    else:
        colormap.setName(style.colormapLut)
    return colormap


def updateDisplayedChannelNames(
    plot: plot_model.Plot, scan: scan_model.Scan, channel_names: List[str]
):
    """Helper to update displayed channels without changing the axis."""

    used_items, unneeded_items, expected_new_channels = filterUsedDataItems(
        plot, channel_names
    )

    if isinstance(plot, plot_item_model.ScatterPlot):
        kind = "scatter"
    elif isinstance(plot, plot_item_model.CurvePlot):
        kind = "curve"
    else:
        raise ValueError("This plot type %s is not supported" % type(plot))

    with plot.transaction():
        for item in used_items:
            item.setVisible(True)
        if len(expected_new_channels) > 0:
            for channel_name in expected_new_channels:
                channel = scan.getChannelByName(channel_name)
                if channel is None:
                    # Create an item pointing to a non existing channel
                    channelRef = plot_model.ChannelRef(plot, channel_name)
                    if kind == "scatter":
                        item = plot_item_model.ScatterItem(plot)
                        item.setValueChannel(channelRef)
                    elif kind == "curve":
                        item = plot_item_model.CurveItem(plot)
                        item.setYChannel(channelRef)
                    plot.addItem(item)
                else:
                    if kind == "scatter":
                        item, _updated = createScatterItem(plot, channel)
                    elif kind == "curve":
                        # FIXME: We have to deal with left/right axis
                        # FIXME: Item can't be added without topmaster
                        item, _updated = createCurveItem(plot, channel, yAxis="left")
                    else:
                        assert False
                    assert not _updated
                item.setVisible(True)
        for item in unneeded_items:
            plot.removeItem(item)
