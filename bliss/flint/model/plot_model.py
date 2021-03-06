# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module provides abstract object to model a plot.

A plot identify what we want to display.

It is not directly connected to a scan data, in order to be used to any scan.
But it uses links to channels: `ChannelRef`. The reference is provided by channel
unique names.

Style are managed by a style strategy. Each item displayed will have a style
object cached in the strategy object. Right now a default strategy class provides
the default styles for all the plots.

Plus each item can have an own style, which can constrain the factory, to allow
the user to custom the rendering. It is part of the architecture but not yet part
of the implementation.

.. image:: _static/flint/model/plot_model.png
    :alt: Scan model
    :align: center
"""

from __future__ import annotations
from typing import List
from typing import Any
from typing import Dict
from typing import Optional

import time
import numpy
import enum
import logging
import contextlib
import weakref

from silx.gui import qt
from . import scan_model
from .style_model import Style
from . import style_model


_logger = logging.getLogger(__name__)


class ChangeEventType(enum.Enum):
    """Enumerate the list of attributes which can emit a change event."""

    YAXIS = enum.auto()
    VISIBILITY = enum.auto()
    CUSTOM_STYLE = enum.auto()
    X_CHANNEL = enum.auto()
    Y_CHANNEL = enum.auto()
    MCA_CHANNEL = enum.auto()
    IMAGE_CHANNEL = enum.auto()
    VALUE_CHANNEL = enum.auto()
    SCANS_STORED = enum.auto()
    GROUP_BY_CHANNELS = enum.auto()


class Plot(qt.QObject):
    """Main object do modelize what we want to plot."""

    itemAdded = qt.Signal(object)
    """Emitted when an item was added"""

    itemRemoved = qt.Signal(object)
    """Emitted when an item was removed"""

    structureChanged = qt.Signal()
    """Emitted when the item structure have changed"""

    valueChanged = qt.Signal(object)
    """Emitted when a property from the plot was updated."""

    styleChanged = qt.Signal()
    """Emitted when the style object have changed"""

    itemValueChanged = qt.Signal(object, object)
    """Emitted when a property of an item have changed.

    The first argument received is the item, and the next one is the attribute
    (one value from the enum `ChangeEventType`)."""

    transactionStarted = qt.Signal()
    """Emitted when a transaction have started.

    See `transaction`."""

    transactionFinished = qt.Signal()
    """Emitted when a transaction have finished.

    See `transaction`."""

    def __init__(self, parent=None):
        super(Plot, self).__init__(parent=parent)
        self.__items: List[Item] = []
        self.__styleStrategy: Optional[StyleStrategy] = None
        self.__inTransaction: int = 0
        self.__name = None
        self.__userEditTime = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        # Well, NotStored is really specific to the long term storage
        items = [i for i in self.__items if not isinstance(i, NotStored)]
        state = {"items": items, "style_strategy": self.__styleStrategy}
        return state

    def __setstate__(self, state):
        self.__items = state.pop("items")
        for i in self.__items:
            # Take the ownership of this items
            i._setPlot(self)
            i.setParent(self)
        self.__styleStrategy = state.pop("style_strategy")
        if self.__styleStrategy is not None:
            self.__styleStrategy.setPlot(self)

    def setName(self, name: str):
        """Set the name of the plot."""
        self.__name = name

    def name(self) -> Optional[str]:
        """Returns the name of the plot, if defined."""
        return self.__name

    def tagUserEditTime(self):
        """Tag the model as edited by the user now"""
        self.__userEditTime = time.time()

    def setUserEditTime(self, userEditTime: float):
        """Set a specific user edit time"""
        self.__userEditTime = userEditTime

    def userEditTime(self) -> Optional[float]:
        """Returns the last time the model was edited by the user"""
        return self.__userEditTime

    def isInTransaction(self) -> bool:
        """True if the plot is in a transaction.

        See `transaction`.
        """
        return self.__inTransaction > 0

    @contextlib.contextmanager
    def transaction(self):
        """Context manager to create set of events which should be manage
        together.

        Mostly designed to reduce computation on the redraw side.
        """
        self.__inTransaction += 1
        if self.__inTransaction == 1:
            self.transactionStarted.emit()
        try:
            yield self
        finally:
            self.__inTransaction -= 1
            if self.__inTransaction == 0:
                self.transactionFinished.emit()

    def addItem(self, item: Item):
        item._setPlot(self)
        self.__items.append(item)
        self.itemAdded.emit(item)
        self.invalidateStructure()

    def __itemTree(self, item: Item) -> List[Item]:
        items = [item]
        for i in self.__items:
            if i.isChildOf(item):
                items.append(i)
        return items

    def clear(self):
        with self.transaction():
            for i in reversed(self.__items):
                i._setPlot(None)
                self.itemRemoved.emit(i)
            self.__items = []
        self.invalidateStructure()

    def removeItem(self, item: Item):
        items = self.__itemTree(item)
        with self.transaction():
            for i in items:
                item._setPlot(None)
                self.__items.remove(i)
            for i in items:
                self.itemRemoved.emit(i)
        self.invalidateStructure()

    def items(self) -> List[Item]:
        # FIXME better to export iterator or read only list
        return self.__items

    def isEmpty(self) -> bool:
        return len(self.__items) == 0

    def invalidateStructure(self):
        """Called by the plot or items when the structure of the plot (item tree)
        have changed."""
        self.__invalidateStyleStrategy()
        self.structureChanged.emit()

    def itemValueWasChanged(self, item, eventType: ChangeEventType):
        if eventType == ChangeEventType.CUSTOM_STYLE:
            self.__invalidateStyleStrategy()
        self.itemValueChanged.emit(item, eventType)

    def styleStrategy(self):
        """Returns the style strategy used by this plot."""
        return self.__styleStrategy

    def __invalidateStyleStrategy(self):
        if self.__styleStrategy is None:
            return
        self.__styleStrategy.invalidateStyles()

    def setStyleStrategy(self, styleStrategy: StyleStrategy):
        """Set the style strategy which have to be used by this plot."""
        self.__styleStrategy = styleStrategy
        self.__styleStrategy.setPlot(self)
        self.styleChanged.emit()

    def __str__(self):
        return "<%s>%s</>" % (
            type(self).__name__,
            "".join([str(i) for i in self.__items]),
        )

    def hasSameTarget(self, other: Plot) -> bool:
        if type(self) is not type(other):
            return False
        if self.__name != other.name():
            return False
        return True


class NotStored:
    """Flag object which do not have to be stored"""


class NotReused:
    """Flag object which do not have to be reused for next scan"""


class ChannelRef(qt.QObject):
    """Identify a channel by it's name.
    """

    def __init__(self, parent=None, channelName=None):
        super(ChannelRef, self).__init__(parent=parent)
        self.__channelName = channelName

    def __eq__(self, other: Any):
        """"True if the channel name is the same."""
        if not isinstance(other, ChannelRef):
            return
        return self.__channelName == other.name()

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = {"channel_name": self.__channelName}
        return state

    def __setstate__(self, state):
        self.__channelName = state.pop("channel_name")

    def channel(self, scan: Optional[scan_model.Scan]) -> Optional[scan_model.Channel]:
        """Returns the referenced channel in this scan, else None."""
        if scan is None:
            return None
        channel = scan.getChannelByName(self.__channelName)
        return channel

    def displayName(self, scan: Optional[scan_model.Scan]) -> str:
        """Returns the best short name available."""
        if scan is not None:
            channel = scan.getChannelByName(self.__channelName)
            if channel is not None:
                name = channel.displayName()
                if name is not None:
                    return name
        return self.baseName()

    def baseName(self) -> str:
        """Returns the base name of this channel."""
        baseName = self.__channelName.split(":")[-1]
        return baseName

    def name(self) -> str:
        """Returns the full name of this channel."""
        return self.__channelName

    def data(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        """Returns the data referenced by this channel inside this scan.

        Returns None if the channel is not found, or the data is  None.
        """
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        return channel.data()

    def array(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        """Returns the `numpy.array` referenced by this channel inside this scan.

        Returns None if the channel is not found, or the data is  None.
        """
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        data = channel.data()
        if data is None:
            return None
        return data.array()

    def __str__(self):
        return "<ChannelRef: %s>" % self.__channelName


class Item(qt.QObject):
    """Describe a generic item provided by plots.
    """

    valueChanged = qt.Signal(ChangeEventType)
    """Emitted when one attribute of the item have changed."""

    def __init__(self, parent=None):
        super(Item, self).__init__(parent=parent)
        self.__isVisible: bool = True
        self.__plotRef: Optional[Plot] = None
        self.__version = 0
        self.__customStyle: Optional[style_model.Style] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = {"visible": self.__isVisible, "style": self.__customStyle}
        return state

    def __setstate__(self, state):
        self.setVisible(state.pop("visible"))
        self.setCustomStyle(state.pop("style"))

    def copy(self, parent):
        state = self.__getstate__()
        newItem = type(self)(parent)
        newItem.__setstate__(state)
        return newItem

    def version(self) -> int:
        """Version of this item.

        Every time one of the attribute of the item is changed, this value is
        incremented."""
        return self.__version

    def isValid(self):
        """Returns true if all the mandatory attributes of this items are set.

        It means that this item have a meaning.
        """
        return True

    def getScanValidation(self, scan: scan_model.Scan) -> Optional[str]:
        """
        Returns None if everything is fine, else a message to explain the problem.
        """
        return None

    def isAvailableInScan(self, scan: scan_model.Scan) -> bool:
        """Returns true if this item is available in this scan.

        This only imply that the data source is available.
        """
        return True

    def isValidInScan(self, scan: scan_model.Scan) -> bool:
        """Returns true if this item do not have any messages associated with
        the data of this scan."""
        return self.getErrorMessage(scan) is None

    def getErrorMessage(self, scan: scan_model.Scan) -> Optional[str]:
        """Returns a message associated to the validation of this item.

        A None result mean that the item is valid in the context of this scan.
        """
        if not scan.hasCacheValidation(self, self.version()):
            result: Optional[str] = self.getScanValidation(scan)
            scan.setCacheValidation(self, self.version(), result)
        else:
            result = scan.getCacheValidation(self, self.version())
        return result

    def isChildOf(self, parent: Item) -> bool:
        """Returns true if this `parent` item is the parent of this item."""
        return False

    def _setPlot(self, plot: Optional[Plot]):
        if plot is None:
            self.__plotRef = None
        else:
            self.__plotRef = weakref.ref(plot)

    def plot(self) -> Optional[Plot]:
        """Returns the plot containing this item."""
        ref = self.__plotRef
        if ref is None:
            return None
        plot = ref()
        if plot is None:
            self.__plotRef = None
        return plot

    def _emitValueChanged(self, eventType: ChangeEventType):
        self.__version = (self.__version + 1) % 0x1000000
        plot = self.plot()
        if plot is not None:
            plot.itemValueWasChanged(self, eventType)
        self.valueChanged.emit(eventType)

    def setVisible(self, isVisible: bool):
        """Set the visibility property of this item."""
        if self.__isVisible == isVisible:
            return
        self.__isVisible = isVisible
        self._emitValueChanged(ChangeEventType.VISIBILITY)

    def isVisible(self) -> bool:
        """Returns true if this item is visible."""
        return self.__isVisible

    def setCustomStyle(self, style: style_model.Style):
        if self.__customStyle == style:
            return
        self.__customStyle = style
        self._emitValueChanged(ChangeEventType.CUSTOM_STYLE)

    def customStyle(self) -> style_model.Style:
        return self.__customStyle

    def getStyle(self, scan: scan_model.Scan = None) -> style_model.Style:
        """Returns the style of this item."""
        plot = self.parent()
        strategy = plot.styleStrategy()
        # FIXME: It means the architecture is not nice
        try:
            return strategy.getStyleFromItem(self, scan)
        except Exception:
            # FIXME: This exception catch should be more accurate than Exception
            return strategy.getStyleFromItem(self, None)


_NotComputed = object()
"""Allow to flag an attribute as not computed"""


class ComputeError(Exception):
    """Raised when the `compute` method of ComputableMixIn or
    IncrementalComputableMixIn can't compute any output"""

    def __init__(self, msg: str, result=None):
        super(ComputeError, self).__init__(self, msg)
        self.msg = msg
        self.result = result


class ChildItem(Item):
    """An item with a source"""

    def __init__(self, parent=None):
        super(ChildItem, self).__init__(parent=parent)
        self.__source: Optional[Item] = None

    def __getstate__(self):
        state: Dict[str, Any] = {}
        state.update(Item.__getstate__(self))
        assert "source" not in state
        state["source"] = self.__source
        return state

    def __setstate__(self, state):
        Item.__setstate__(self, state)
        self.__source = state.pop("source")

    def copy(self, parent):
        state = self.__getstate__()
        newItem = type(self)(parent)
        state["source"] = None
        newItem.__setstate__(state)
        return newItem

    def isChildOf(self, parent: Item) -> bool:
        source = self.source()
        if source is parent:
            return True
        if source.isChildOf(parent):
            return True
        return False

    def setSource(self, source: Item):
        self.__source = source
        # FIXME: A structural change on the source item have to invalidate the result

    def source(self) -> Optional[Item]:
        return self.__source

    def isAvailableInScan(self, scan: scan_model.Scan) -> bool:
        """Returns true if this item is available in this scan.

        This only imply that the data source is available.
        """
        if not self.isValid():
            return False
        source = self.source()
        if source is not None:
            if not source.isAvailableInScan(scan):
                return False
        return True


class ComputableMixIn:
    """This item use the scan data to process result before displaying it."""

    resultAvailable = qt.Signal(object)

    def inputData(self) -> Any:
        """Needed to invalidate the data according to the configuration"""
        return None

    def isResultComputed(self, scan: scan_model.Scan) -> bool:
        return scan.hasCachedResult(self)

    def reachResult(self, scan: scan_model.Scan):
        # FIXME: implement an asynchronous the cache system
        # FIXME: cache system have to be invalidated when self config changes
        key = (self, self.inputData())
        if scan.hasCachedResult(key):
            result = scan.getCachedResult(key)
        else:
            try:
                result = self.compute(scan)
            except ComputeError as e:
                try:
                    # FIXME: This messages should be stored at the same place
                    scan.setCacheValidation(self, self.version(), e.msg)
                except KeyError:
                    _logger.error(
                        "Computation message lost: %s, %s, %s",
                        self,
                        self.version(),
                        e.msg,
                    )

                result = e.result
            except Exception as e:
                scan.setCacheValidation(
                    self, self.version(), "Error while computing:" + str(e)
                )
                result = None

            scan.setCachedResult(key, result)
        if not self.isResultValid(result):
            return None
        return result

    def compute(self, scan: scan_model.Scan) -> Any:
        raise NotImplementedError()

    def isResultValid(self, result: Any) -> bool:
        raise NotImplementedError()


class IncrementalComputableMixIn(ComputableMixIn):
    def incrementalCompute(self, previousResult: Any, scan: scan_model.Scan) -> Any:
        """Compute a data using the previous value as basis"""
        raise NotImplementedError()


class StyleStrategy:
    """"Compute and store styles used by items from a plot"""

    def __init__(self):
        self.__plotRef: Optional[Plot] = None

    def __reduce__(self):
        return (self.__class__, ())

    def setPlot(self, plot: Plot):
        if plot is not None:
            self.__plotRef = weakref.ref(plot)
        else:
            self.__plotRef = None
        self.invalidateStyles()

    def plot(self) -> Optional[Plot]:
        """Returns the plot in which this style is applied."""
        ref = self.__plotRef
        if ref is None:
            return None
        plot = ref()
        if plot is None:
            self.__plotRef = None
        return plot

    def invalidateStyles(self):
        pass

    def computeItemStyleFromPlot(self):
        pass

    def getStyleFromItem(self, item: Item, scan: scan_model.Scan = None) -> Style:
        raise NotImplementedError()
