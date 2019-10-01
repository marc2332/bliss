# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

from . import plot_model


class McaPlot(plot_model.Plot):
    pass


class McaItem(plot_model.Item):
    def __init__(self, parent: plot_model.Plot = None):
        super(McaItem, self).__init__(parent=parent)
        self.__mca: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(McaItem, self).__getstate__()
        return (state, self.__mca)

    def __setstate__(self, state):
        super(McaItem, self).__setstate__(state[0])
        self.__mca = state[1]

    def isValid(self):
        return self.__mca is not None

    def mcaChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__mca

    def setMcaChannel(self, channel: plot_model.ChannelRef):
        self.__mca = channel
        self._emitValueChanged(plot_model.ChangeEventType.MCA_CHANNEL)


class ImagePlot(plot_model.Plot):
    pass


class ImageItem(plot_model.Item):
    def __init__(self, parent: plot_model.Plot = None):
        super(ImageItem, self).__init__(parent=parent)
        self.__image: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(ImageItem, self).__getstate__()
        return (state, self.__image)

    def __setstate__(self, state):
        super(ImageItem, self).__setstate__(state[0])
        self.__image = state[1]

    def isValid(self):
        return self.__image is not None

    def imageChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__image

    def setImageChannel(self, channel: plot_model.ChannelRef):
        self.__image = channel
        self._emitValueChanged(plot_model.ChangeEventType.IMAGE_CHANNEL)
