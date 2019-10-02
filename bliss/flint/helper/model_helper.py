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

from bliss.flint.model import plot_model
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
    if xChannel is None:
        return None
    x = xChannel.name()
    channelX = scan.getChannelByName(x)
    if channelX is None:
        return None

    yChannel = plotItem.yChannel()
    if yChannel is None:
        # Without y, the item is still valid
        topMasterX = channelX.device().topMaster()
        return topMasterX

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
