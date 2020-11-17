# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
This module contains extra ROIs inherited from silx
"""
import enum
import logging
import numpy

import silx.gui.plot.items.roi as silx_rois
from silx.gui.plot import items
from silx.gui.colors import rgba

_logger = logging.getLogger(__name__)


class LimaRectRoi(silx_rois.RectangleROI):
    """Rectangle ROI used to configure Lima detector.

    It is used to count sum, avg, min, max
    """

    def __init__(self, parent=None):
        silx_rois.RectangleROI.__init__(self, parent=parent)
        self.sigEditingFinished.connect(self.__normalizeGeometry)

    def setFirstShapePoints(self, points):
        # Normalize the ROI position to the pixel
        points = points.astype(int)
        silx_rois.RectangleROI.setFirstShapePoints(self, points)

    def __normalizeGeometry(self):
        # Normalize the ROI position to the pixel
        pixelcenter = numpy.array([0.5, 0.5])
        pos1 = self.getOrigin()
        pos2 = (pos1 + self.getSize() + pixelcenter).astype(int)
        pos1 = (pos1 + pixelcenter).astype(int)
        self.setGeometry(origin=pos1, size=pos2 - pos1)


class LimaArcRoi(silx_rois.ArcROI):
    """Arc ROI used to configure Lima detector.

    It is used to count sum, avg, min, max
    """


class LimaProfileRoi(silx_rois.RectangleROI):
    """Rectangle ROI used to configure Lima detector.

    It is used to compute a vertical or horizontal profile.
    """

    class Directions(enum.Enum):
        VERTICAL_REDUCTION = "vertical-reduction"
        HORIZONTAL_REDUCTION = "horizontal-reduction"

    def __init__(self, parent=None):
        super(LimaProfileRoi, self).__init__(parent=parent)
        self.__limaKind = self.Directions.VERTICAL_REDUCTION
        line = items.Shape("polylines")
        # line.setPoints([[0, 0], [0, 0]])
        line.setOverlay(True)
        line.setLineStyle(self.getLineStyle())
        line.setLineWidth(self.getLineWidth())
        line.setColor(rgba(self.getColor()))
        self.__line = line
        self.addItem(line)
        symbol = items.Marker()
        symbol.setColor(rgba(self.getColor()))
        self.addItem(symbol)
        self.__symbol = symbol
        self.__updateOverlay()
        self.sigRegionChanged.connect(self.__regionChanged)

    def _updated(self, event=None, checkVisibility=True):
        if event in [items.ItemChangedType.VISIBLE]:
            self._updateItemProperty(event, self, self.__line)
        super(LimaProfileRoi, self)._updated(event, checkVisibility)

    def _updatedStyle(self, event, style):
        super(LimaProfileRoi, self)._updatedStyle(event, style)
        self.__line.setColor(style.getColor())
        self.__line.setLineStyle(style.getLineStyle())
        self.__line.setLineWidth(style.getLineWidth())
        self.__symbol.setColor(style.getColor())

    def __regionChanged(self):
        self.__updateOverlay()

    def setLimaKind(self, direction):
        if self.__limaKind == direction:
            return
        self.__limaKind = direction
        self.__updateOverlay()

    def getLimaKind(self):
        return self.__limaKind

    def __updateOverlay(self):
        x, y = self.getCenter()
        w, h = self.getSize()
        w, h = w / 2, h / 2
        if self.__limaKind == self.Directions.HORIZONTAL_REDUCTION:
            points = [[x - w, y], [x + w, y]]
            symbol = "caretright"
        elif self.__limaKind == self.Directions.VERTICAL_REDUCTION:
            points = [[x, y - h], [x, y + h]]
            symbol = "caretdown"
        else:
            assert False
        self.__line.setPoints(points)
        self.__symbol.setSymbol(symbol)
        self.__symbol.setPosition(*points[1])


class LimaHProfileRoi(LimaProfileRoi):
    """
    Lima ROI for horizontal profile.

    It displays a rectangle ROI with extra overlay to show that there is
    a vertical reduction of the data.
    """

    ICON = "flint:icons/add-vreduction"
    NAME = "vreduction"
    SHORT_NAME = "vertical reduction"

    def __init__(self, parent=None):
        LimaProfileRoi.__init__(self, parent=parent)
        self.setLimaKind(LimaProfileRoi.Directions.VERTICAL_REDUCTION)


class LimaVProfileRoi(LimaProfileRoi):
    """
    Lima ROI for vertical profile.

    It displays a rectangle ROI with extra overlay to show that there is
    a horizontal reduction of the data.
    """

    ICON = "flint:icons/add-hreduction"
    NAME = "hreduction"
    SHORT_NAME = "horizontal reduction"

    def __init__(self, parent=None):
        LimaProfileRoi.__init__(self, parent=parent)
        self.setLimaKind(LimaProfileRoi.Directions.HORIZONTAL_REDUCTION)
