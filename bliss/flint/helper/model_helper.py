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

from bliss.flint.model import plot_model, plot_item_model
from bliss.flint.model import plot_curve_model
from bliss.flint.model import scan_model


def reachAnyCurveItemFromDevice(
    plot: plot_model.Plot, scan: scan_model.Scan, topMaster: scan_model.Device
) -> Optional[plot_curve_model.CurveItem]:
    """
    Reach any plot item from this top master
    """
    for item in plot.items():
        if not isinstance(item, plot_curve_model.CurveItem):
            continue
        xChannel = item.xChannel()
        assert xChannel is not None
        channelName = xChannel.name()
        channel = scan.getChannelByName(channelName)
        assert channel is not None
        itemMaster = channel.device().topMaster()
        if itemMaster is topMaster:
            return item
    return None


def reachAllCurveItemFromDevice(
    plot: plot_model.Plot, scan: scan_model.Scan, topMaster: scan_model.Device
) -> List[plot_curve_model.CurveItem]:
    """
    Reach all plot items from this top master
    """
    curves = []
    for item in plot.items():
        if not isinstance(item, plot_curve_model.CurveItem):
            continue
        xChannel = item.xChannel()
        assert xChannel is not None
        channelName = xChannel.name()
        channel = scan.getChannelByName(channelName)
        assert channel is not None
        itemMaster = channel.device().topMaster()
        if itemMaster is topMaster:
            curves.append(item)
    return curves


def getConsistentTopMaster(
    scan: scan_model.Scan, plotItem: plot_curve_model.CurveItem
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
    scan: scan_model.Scan, plotModel: plot_curve_model.CurvePlot
) -> Dict[scan_model.Device, str]:
    """"
    Returns a dictionary mapping top master with the most used x-channels.
    """
    if scan is None:
        return {}
    if plotModel is None:
        return {}

    # Count the amount of same x-channel per top masters
    xChannelsPerMaster: Dict[scan_model.Device, Dict[str, int]] = {}
    for plotItem in plotModel.items():
        if not isinstance(plotItem, plot_curve_model.CurveItem):
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
        channels = sorted(counts.keys(), key=lambda x: counts[x])
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
    elif isinstance(item, plot_curve_model.CurveItem):
        xChannel = item.xChannel()
        if xChannel is not None:
            # Reach curves sharing the same x-channel
            curves = []
            for curve in plot.items():
                if isinstance(curve, plot_curve_model.CurveItem):
                    if xChannel == curve.xChannel():
                        curves.append(curve)

            if len(curves) == 1:
                # Only remove the value to remember the axes
                xChannel = cloneChannelRef(plot, xChannel)
                newItem = plot_curve_model.CurveItem(plot)
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
            baseItem.setValueChannel(plot_model.ChannelRef(plot, channel.name()))
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
            newItem.setValueChannel(plot_model.ChannelRef(plot, channel.name()))
    else:
        # No axes are specified
        # FIXME: Maybe we could use scan infos to reach the default axes
        newItem = plot_item_model.ScatterItem(plot)
        newItem.setValueChannel(plot_model.ChannelRef(plot, channel.name()))
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
            newItem = plot_curve_model.CurveItem(plot)
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

        newItem = plot_curve_model.CurveItem(plot)
        newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
        newItem.setYChannel(plot_model.ChannelRef(plot, channel.name()))
        newItem.setYAxis(yAxis)

    plot.addItem(newItem)
    return newItem, False
