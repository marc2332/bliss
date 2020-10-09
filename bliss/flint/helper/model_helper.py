# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Helper functions to deal with Flint models
"""

from __future__ import annotations
from typing import Optional
from typing import List
from typing import Set
from typing import Dict
from typing import Tuple

import logging

from silx.gui import colors

from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.model import style_model


_logger = logging.getLogger(__name__)


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


def getChannelNameGroups(scan: scan_model.Scan) -> List[Set[str]]:
    """Returns the list of channels which are in the same group.

    A group is supposed to contain only channels with, in the end, the same
    amount of measurements.
    """
    channels: Dict[scan_model.Device, List[scan_model.Channel]] = {}
    for device in scan.devices():
        if device.isMaster():
            channels[device] = list(device.channels())
        else:
            topMaster = device.topMaster()
            channels[topMaster].extend(device.channels())

    result: List[Set[str]] = []
    for data in channels.values():
        ch = [c.name() for c in data]
        result.append(ch)
    return result


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
) -> Tuple[plot_item_model.ScatterItem, bool]:
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
        elif isinstance(item, plot_item_model.ImageItem):
            channel = item.imageChannel()
        elif isinstance(item, plot_item_model.McaItem):
            channel = item.mcaChannel()
        else:
            _logger.debug("Item %s skipped", type(item))
            continue
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


def removeNotAvailableChannels(
    plot: plot_model.Plot, basePlot: plot_model.Plot, baseScan: scan_model.Scan
):
    """Remove from `plot` channels which are not available in this `scan`.
    The `basePlot` generated from this `scan` can help to improve the result.

    As result:

    - Channels used as value by `plot` have to exist in the scan
    - Axes also have to exists
        - Else it is reach from the basePlot
            - Else there is none
    """
    groups = getChannelNameGroups(baseScan)

    def findGroupId(name: str):
        for groupId, group in enumerate(groups):
            if name in group:
                return groupId
        return None

    # Try to identify the default axis for each groups
    defaultAxis = [None] * len(groups)
    for item in basePlot.items():
        xChannel = item.xChannel()
        if xChannel is None:
            continue
        yChannel = item.yChannel()
        if yChannel is not None:
            groupId = findGroupId(yChannel.name())
            if groupId is not None:
                defaultAxis[groupId] = xChannel.name()

    def isConsistent(item):
        xChannel = item.xChannel()
        yChannel = item.yChannel()
        if xChannel is None:
            return False
        if yChannel is None:
            return False
        g1 = findGroupId(xChannel.name())
        g2 = findGroupId(yChannel.name())
        if g1 is None or g2 is None:
            # Not supposed to happen
            assert False
        return g1 == g2

    def getDefaultAxis(name: str):
        g = findGroupId(name)
        if g is None:
            return None
        return defaultAxis[g]

    available = set([])
    for g in groups:
        available.update(g)

    with plot.transaction():
        for item in plot.items():
            if isinstance(item, plot_item_model.CurveItem):
                # If y is not available the item have no meaning
                yChannel = item.yChannel()
                if yChannel is not None:
                    if yChannel.name() not in available:
                        plot.removeItem(item)
                        continue

                # If x is not there we still can do something
                xChannel = item.xChannel()
                if xChannel is not None:
                    if xChannel.name() not in available:
                        if yChannel is None:
                            plot.removeItem(item)
                            continue
                        else:
                            item.setXChannel(None)

                if yChannel is not None and not isConsistent(item):
                    # We have to found a new axis
                    axisName = getDefaultAxis(yChannel.name())
                    if axisName is None:
                        item.setXChannel(None)
                    else:
                        channel = plot_model.ChannelRef(item, axisName)
                        item.setXChannel(channel)


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
            if m.axisId == 0:
                return channel
    return None


def getColormapFromItem(
    item: plot_model.Item,
    style: style_model.Style,
    defaultColormap: Optional[colors.Colormap] = None,
) -> colors.Colormap:
    """Returns the colormap from an item, taking care of the cache.
    """
    colormap = item.colormap()
    if colormap is None:
        if defaultColormap is None:
            # Store the colormap
            # FIXME as the colormap is exposed to the colormap dialog
            # it have to be synchronized to the item style
            colormap = colors.Colormap(style.colormapLut)
        else:
            colormap = defaultColormap
        item.setColormap(colormap)
    else:
        if colormap is defaultColormap:
            # The default colormap must not be changed
            pass
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

    unneeded_items = set(unneeded_items)
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
                        item, updated = createScatterItem(plot, channel)
                        if updated:
                            unneeded_items.discard(item)
                    elif kind == "curve":
                        # FIXME: We have to deal with left/right axis
                        # FIXME: Item can't be added without topmaster
                        item, updated = createCurveItem(plot, channel, yAxis="left")
                        if updated:
                            unneeded_items.discard(item)
                    else:
                        assert False
                item.setVisible(True)
        for item in unneeded_items:
            plot.removeItem(item)


def copyItemsFromChannelNames(
    sourcePlot: plot_model.Plot, destinationPlot: plot_model.Plot
):
    """Copy from the source plot the item which was setup into the destination plot"""
    if not isinstance(sourcePlot, plot_item_model.CurvePlot):
        raise TypeError("Only available for curve plot. Found %s" % type(sourcePlot))
    if not isinstance(destinationPlot, type(sourcePlot)):
        raise TypeError(
            "Both plots must have the same type. Found %s" % type(destinationPlot)
        )

    availableItems = {}
    for item in sourcePlot.items():
        if isinstance(item, plot_item_model.CurveItem):
            channel = item.yChannel()
            if channel is None:
                continue
            name = channel.name()
            availableItems[name] = item

    with destinationPlot.transaction():
        for item in destinationPlot.items():
            if isinstance(item, plot_item_model.CurveItem):
                channel = item.yChannel()
                if channel is None:
                    continue
                name = channel.name()
                sourceItem = availableItems.get(name)
                if sourceItem is not None:
                    copyItemConfig(sourceItem, item)


def copyItemConfig(sourceItem: plot_model.Item, destinationItem: plot_model.Item):
    """Copy the configuration and the item tree from a source item to a
    destination item"""
    if not isinstance(sourceItem, plot_item_model.CurveItem):
        raise TypeError("Only available for curve item. Found %s" % type(sourceItem))
    if not isinstance(destinationItem, type(sourceItem)):
        raise TypeError(
            "Both items must have the same type. Found %s" % type(destinationItem)
        )

    destinationItem.setYAxis(sourceItem.yAxis())

    sourceToDest = {}
    sourceToDest[sourceItem] = destinationItem

    destinationPlot = destinationItem.plot()
    for item in sourceItem.plot().items():
        if item.isChildOf(sourceItem):
            newItem = item.copy(destinationPlot)
            newItem.setParent(destinationPlot)
            destinationSource = sourceToDest[item.source()]
            newItem.setSource(destinationSource)
            destinationPlot.addItem(newItem)
            sourceToDest[item] = newItem
