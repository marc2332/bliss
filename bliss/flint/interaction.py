# coding: utf-8


from __future__ import division, absolute_import, print_function, unicode_literals


import six

from silx.gui import qt, icons
from silx.gui.plot.actions import PlotAction, mode
from silx.gui.plot import PlotWindow, PlotWidget
from silx.gui.plot.Colors import rgba


class DrawModeAction(PlotAction):
    """Action that control drawing mode"""

    _MODES = {  # shape: (icon, text, tooltip
        'rectangle': ('shape-rectangle', 'Rectangle selection', 'Select a rectangular region'),
        'line': ('shape-diagonal', 'Line selection', 'Select a line'),
        'hline': ('shape-horizontal', 'H. line selection', 'Select a horizontal line'),
        'vline': ('shape-vertical', 'V. line selection', 'Select a vertical line'),
        'polygon': ('shape-polygon', 'Polygon selection', 'Select a polygon'),
    }

    def __init__(self, plot, parent=None):
        self._shape = 'polygon'
        self._label = None
        self._color = 'black'
        self._width = None
        icon, text, tooltip = self._MODES[self._shape]

        super(DrawModeAction, self).__init__(
            plot, icon=icon, text=text,
            tooltip=tooltip,
            triggered=self._actionTriggered,
            checkable=True, parent=parent)

        # Listen to mode change
        self.plot.sigInteractiveModeChanged.connect(self._modeChanged)
        # Init the state
        self._modeChanged(None)

    def _update(self):
        if self.isChecked():
            self._actionTriggered()

    def setShape(self, shape):
        self._shape = shape
        icon, text, tooltip = self._MODES[self._shape]
        self.setIcon(icons.getQIcon(icon))
        self.setText(text)
        self.setToolTip(tooltip)
        self._update()

    def getShape(self):
        return self._shape

    def setColor(self, color):
        self._color = rgba(color)
        self._update()

    def getColor(self):
        return qt.QColor.fromRgbF(*self._color)

    def setLabel(self, label):
        self._label = label
        self._update()

    def getLabel(self):
        return self._label

    def setWidth(self, width):
        self._width = width
        self._update()

    def getWidth(self):
        return self._width

    def _modeChanged(self, source):
        modeDict = self.plot.getInteractiveMode()
        old = self.blockSignals(True)
        self.setChecked(modeDict['mode'] == 'draw' and
                        modeDict['shape'] == self._shape and
                        modeDict['label'] == self._label)
        self.blockSignals(old)

    def _actionTriggered(self, checked=False):
        self.plot.setInteractiveMode('draw',
                                     source=self,
                                     shape=self._shape,
                                     color=self._color,
                                     label=self._label,
                                     width=self._width)


class ShapeSelector(qt.QObject):
    """Handles the selection of a single shape in a PlotWidget

    :param parent: QObject's parent
    """

    selectionChanged = qt.Signal(tuple)
    """Signal emitted whenever the selection has changed.
    
    It provides the selection.
    """

    selectionFinished = qt.Signal(tuple)
    """Signal emitted when selection is terminated.
    
    It provides the selection.
    """

    def __init__(self, parent=None):
        assert isinstance(parent, PlotWidget)
        super(ShapeSelector, self).__init__(parent)
        self._isSelectionRunning = False
        self._selection = ()
        self._itemId = "%s-%s" % (self.__class__.__name__, id(self))

        # Add a toolbar to plot
        self._toolbar = qt.QToolBar('Selection')
        self._modeAction = DrawModeAction(plot=parent)
        self._modeAction.setLabel(self._itemId)
        self._modeAction.setColor(rgba('red'))
        toolButton = qt.QToolButton()
        toolButton.setDefaultAction(self._modeAction)
        toolButton.setToolButtonStyle(qt.Qt.ToolButtonTextBesideIcon)
        self._toolbar.addWidget(toolButton)

    # Style

    def getColor(self):
        """Returns the color used for the selection shape

        :rtype: QColor
        """
        return self._modeAction.getColor()

    def setColor(self, color):
        """Set the color used for the selection shape

        :param color: The color to use for selection shape as
           either a color name, a QColor, a list of uint8 or float in [0, 1].
        """
        self._modeAction.setColor(color)
        self._updateShape()

    # Control selection

    def getSelection(self):
        """Returns selection control point coordinates

        Returns an empty tuple if there is no selection

        :return: Nx2 (x, y) coordinates or an empty tuple.
        """
        return tuple(zip(*self._selection))

    def _setSelection(self, x, y):
        """Set the selection shape control points.

        Use :meth:`reset` to remove the selection.

        :param x: X coordinates of control points
        :param y: Y coordinates of control points
        """
        selection = x, y
        if selection != self._selection:
            self._selection = selection
            self._updateShape()
            self.selectionChanged.emit(self.getSelection())

    def reset(self):
        """Clear the rectangle selection"""
        if self._selection:
            self._selection = ()
            self._updateShape()
            self.selectionChanged.emit(self.getSelection())

    def start(self, shape):
        """Start requiring user to select a rectangle

        :param str shape: The shape to select in:
            'rectangle', 'line', 'polygon', 'hline', 'vline'
        """
        plot = self.parent()
        if plot is None:
            raise RuntimeError('No plot to perform selection')

        self.stop()
        self.reset()

        assert shape in ('rectangle', 'line', 'polygon', 'hline', 'vline')

        self._modeAction.setShape(shape)
        self._modeAction.trigger()  # To set the interaction mode

        self._isSelectionRunning = True

        plot.sigPlotSignal.connect(self._handleDraw)

        self._toolbar.show()
        plot.addToolBar(qt.Qt.BottomToolBarArea, self._toolbar)

    def stop(self):
        """Stop shape selection"""
        if not self._isSelectionRunning:
            return

        plot = self.parent()
        if plot is None:
            return

        mode = plot.getInteractiveMode()
        if mode['mode'] == 'draw' and mode['label'] == self._itemId:
            plot.setInteractiveMode('zoom')  # This disconnects draw handler

        plot.sigPlotSignal.disconnect(self._handleDraw)

        plot.removeToolBar(self._toolbar)

        self._isSelectionRunning = False
        self.selectionFinished.emit(self.getSelection())

    def _handleDraw(self, event):
        """Handle shape drawing event"""
        if (event['event'] == 'drawingFinished' and
                event['parameters']['label'] == self._itemId):
            self._setSelection(event['xdata'], event['ydata'])
            self.stop()

    def _updateShape(self):
        """Update shape on the plot"""
        plot = self.parent()
        if plot is not None:
            if not self._selection:
                plot.remove(legend=self._itemId, kind='item')

            else:
                x, y = self._selection
                shape = self._modeAction.getShape()
                if shape == 'line':
                    shape = 'polylines'

                plot.addItem(x, y,
                             legend=self._itemId,
                             shape=shape,
                             color=rgba(self._modeAction.getColor()),
                             fill=False)



class PointsSelector(qt.QObject):
    """Handle selection of points in a PlotWidget"""

    selectionChanged = qt.Signal(tuple)
    """Signal emitted whenever the selection has changed.
    
    It provides the selection.
    """

    selectionFinished = qt.Signal(tuple)
    """Signal emitted when selection is terminated.
    
    It provides the selection.
    """


    def __init__(self, parent):
        assert isinstance(parent, PlotWidget)
        super(PointsSelector, self).__init__(parent)

        self._isSelectionRunning = False
        self._markersAndPos = []
        self._totalPoints = 0

    def getSelection(self):
        """Returns the selection"""
        return tuple(pos for _, pos in self._markersAndPos)

    def eventFilter(self, obj, event):
        """Event filter for plot hide and key event"""
        if event.type() == qt.QEvent.Hide:
            self.stop()

        elif event.type() == qt.QEvent.KeyPress:
            if event.key() in (qt.Qt.Key_Delete, qt.Qt.Key_Backspace) or (
                    event.key() == qt.Qt.Key_Z and event.modifiers() & qt.Qt.ControlModifier):
                if len(self._markersAndPos) > 0:
                    plot = self.parent()
                    if plot is not None:
                        legend, _ = self._markersAndPos.pop()
                        plot.remove(legend=legend, kind='marker')

                        self._updateStatusBar()
                        self.selectionChanged.emit(self.getSelection())
                        return True  # Stop further handling of those keys

            elif event.key() == qt.Qt.Key_Return:
                self.stop()
                return True  # Stop further handling of those keys

        return super(PointsSelector, self).eventFilter(obj, event)

    def start(self, nbPoints=1):
        """Start interactive selection of points

        :param int nbPoints: Number of points to select
        """
        self.stop()
        self.reset()

        plot = self.parent()
        if plot is None:
            raise RuntimeError('No plot to perform selection')

        self._totalPoints = nbPoints
        self._isSelectionRunning = True

        plot.setInteractiveMode(mode='zoom')
        self._handleInteractiveModeChanged(None)
        plot.sigInteractiveModeChanged.connect(
            self._handleInteractiveModeChanged)

        plot.installEventFilter(self)

        self._updateStatusBar()

    def stop(self):
        """Stop interactive point selection"""
        if not self._isSelectionRunning:
            return

        plot = self.parent()
        if plot is None:
            return

        plot.removeEventFilter(self)

        plot.sigInteractiveModeChanged.disconnect(
            self._handleInteractiveModeChanged)

        currentMode = plot.getInteractiveMode()
        if currentMode['mode'] == 'zoom':  # Stop handling mouse click
            plot.sigPlotSignal.disconnect(self._handleSelect)

        plot.statusBar().clearMessage()
        self._isSelectionRunning = False
        self.selectionFinished.emit(self.getSelection())

    def reset(self):
        """Reset selected points"""
        plot = self.parent()
        if plot is None:
            return

        for legend, _ in self._markersAndPos:
            plot.remove(legend=legend, kind='marker')
        self._markersAndPos = []
        self.selectionChanged.emit(self.getSelection())

    def _updateStatusBar(self):
        """Update status bar message"""
        plot = self.parent()
        if plot is None:
            return

        msg = 'Select %d/%d input points' % (len(self._markersAndPos),
                                             self._totalPoints)

        currentMode = plot.getInteractiveMode()
        if currentMode['mode'] != 'zoom':
            msg += ' (Use zoom mode to add/remove points)'

        plot.statusBar().showMessage(msg)

    def _handleSelect(self, event):
        """Handle mouse events"""
        if event['event'] == 'mouseClicked' and event['button'] == 'left':
            plot = self.parent()
            if plot is None:
                return

            x, y = event['x'], event['y']

            # Add marker
            legend = "sx.ginput %d" % len(self._markersAndPos)
            plot.addMarker(
                x, y,
                legend=legend,
                text='%d' % len(self._markersAndPos),
                color='red',
                draggable=False)

            self._markersAndPos.append((legend, (x, y)))
            self._updateStatusBar()
            if len(self._markersAndPos) >= self._totalPoints:
                self.stop()

    def _handleInteractiveModeChanged(self, source):
        """Handle change of interactive mode in the plot

        :param source: Objects that triggered the mode change
        """
        plot = self.parent()
        if plot is None:
            return

        mode = plot.getInteractiveMode()
        if mode['mode'] == 'zoom':  # Handle click events
            plot.sigPlotSignal.connect(self._handleSelect)
        else:  # Do not handle click event
            plot.sigPlotSignal.disconnect(self._handleSelect)
        self._updateStatusBar()


# TODO refactor to make a selection by composition rather than inheritance...
class BlissPlot(PlotWindow):
    """Plot with selection methods"""

    sigSelectionDone = qt.Signal(object)
    """Signal emitted when the selection is done
    
    It provides the list of selected points
    """

    def __init__(self, parent=None, **kwargs):
        super(BlissPlot, self).__init__(parent=parent, **kwargs)
        self._selectionColor = rgba('red')
        self._selectionMode = None
        self._markers = []
        self._pointNames = ()

    # Style

    def getColor(self):
        """Returns the color used for selection markers

        :rtype: QColor
        """
        return qt.QColor.fromRgbF(*self._selectionColor)

    def setColor(self, color):
        """Set the markers used for selection

        :param color: The color to use for selection markers as
           either a color name, a QColor, a list of uint8 or float in [0, 1].
        """
        self._selectionColor = rgba(color)
        self._updateMarkers()  # To apply color change

    # Marker helpers

    def _setSelectedPointMarker(self, x, y, index=None):
        """Add/Update a marker for a point

        :param float x: X coord in plot
        :param float y: Y coord in plot
        :param int index: Index of point in points names to set
        :return: corresponding marker legend
        :rtype: str
        """
        if index is None:
            index = len(self._markers)

        name = self._pointNames[index]
        legend = "BlissPlotSelection-%d" % index

        self.addMarker(
            x, y,
            legend=legend,
            text=name,
            color=self._selectionColor,
            draggable=self._selectionMode is not None)
        return legend

    def _updateMarkers(self):
        """Update all markers to sync color/draggable"""
        for index, (x, y) in enumerate(self.getSelectedPoints()):
            self._setSelectedPointMarker(x, y, index)

    # Selection mode control

    def startPointSelection(self, points=1):
        """Request the user to select a number of points

        :param points:
            The number of points the user need to select (default: 1)
            or a list of point names or a single name.
        :type points: Union[int, List[str], str]
        :return: A future to access the result
        :rtype: concurrent.futures.Future
        """
        self.stopSelection()
        self.resetSelection()

        if isinstance(points, six.string_types):
            points = [points]
        elif isinstance(points, int):
            points = [str(i) for i in range(points)]

        self._pointNames = points

        self._markers = []
        self._selectionMode = 'points'

        self.setInteractiveMode(mode='zoom')
        self._handleInteractiveModeChanged(None)
        self.sigInteractiveModeChanged.connect(
            self._handleInteractiveModeChanged)

    def stopSelection(self):
        """Stop current selection.

        Calling this method emits the selection through sigSelectionDone
        and does not clear the selection.
        """
        if self._selectionMode is not None:
            currentMode = self.getInteractiveMode()
            if currentMode['mode'] == 'zoom':  # Stop handling mouse click
                self.sigPlotSignal.disconnect(self._handleSelect)

            self.sigInteractiveModeChanged.disconnect(
                self._handleInteractiveModeChanged)

            self._selectionMode = None
            self.statusBar().showMessage('Selection done')

            self._updateMarkers()  # To make them not draggable

            self.sigSelectionDone.emit(self.getSelectedPoints())

    def getSelectedPoints(self):
        """Returns list of currently selected points

        :rtype: tuple
        """
        return tuple(self._getItem(kind='marker', legend=legend).getPosition()
                     for legend in self._markers)

    def resetSelection(self):
        """Clear current selection"""
        for legend in self._markers:
            self.remove(legend, kind='marker')
        self._markers = []

        if self._selectionMode is not None:
            self._updateStatusBar()
        else:
            self.statusBar().clearMessage()

    def _handleInteractiveModeChanged(self, source):
        """Handle change of interactive mode in the plot

        :param source: Objects that triggered the mode change
        """
        mode = self.getInteractiveMode()
        if mode['mode'] == 'zoom':  # Handle click events
            self.sigPlotSignal.connect(self._handleSelect)
        else:  # Do not handle click event
            self.sigPlotSignal.disconnect(self._handleSelect)
        self._updateStatusBar()

    def _handleSelect(self, event):
        """Handle mouse events"""
        if event['event'] == 'mouseClicked' and event['button'] == 'left':
            if len(self._markers) == len(self._pointNames):
                return

            x, y = event['x'], event['y']
            legend = self._setSelectedPointMarker(x, y, len(self._markers))
            self._markers.append(legend)
            self._updateStatusBar()

    def keyPressEvent(self, event):
        """Handle keys for undo/done actions"""
        if self._selectionMode is not None:
            if event.key() in (qt.Qt.Key_Delete, qt.Qt.Key_Backspace) or (
                    event.key() == qt.Qt.Key_Z and
                    event.modifiers() & qt.Qt.ControlModifier):
                if len(self._markers) > 0:
                    legend = self._markers.pop()
                    self.remove(legend, kind='marker')

                    self._updateStatusBar()
                    return  # Stop processing the event

            elif event.key() == qt.Qt.Key_Return:
                self.stopSelection()
                return  # Stop processing the event

        return super(BlissPlot, self).keyPressEvent(event)

    def _updateStatusBar(self):
        """Update status bar message"""
        if len(self._markers) < len(self._pointNames):
            name = self._pointNames[len(self._markers)]
            msg = 'Select point: %s (%d/%d)' % (
                name, len(self._markers), len(self._pointNames))
        else:
            msg = 'Selection ready. Press Enter to validate'

        currentMode = self.getInteractiveMode()
        if currentMode['mode'] != 'zoom':
            msg += ' (Use zoom mode to add/edit points)'

        self.statusBar().showMessage(msg)


if __name__ == '__main__':
    app = qt.QApplication([])

    #plot = BlissPlot()
    #plot.startPointSelection(('first', 'second', 'third'))

    def dumpChanged(selection):
        print('selectionChanged', selection)

    def dumpFinished(selection):
        print('selectionFinished', selection)

    plot = PlotWindow()
    selector = ShapeSelector(plot)
    #selector.start(shape='rectangle')
    selector.selectionChanged.connect(dumpChanged)
    selector.selectionFinished.connect(dumpFinished)
    plot.show()

    points = PointsSelector(plot)
    points.start(3)
    points.selectionChanged.connect(dumpChanged)
    points.selectionFinished.connect(dumpFinished)
    #app.exec_()
