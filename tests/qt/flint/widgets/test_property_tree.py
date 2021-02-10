"""Testing property tree."""

import pytest

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets import _property_tree_helper


@pytest.mark.usefixtures("xvfb")
class TestImagePlot(TestCaseQt):
    def test_empty(self):
        tree = qt.QTreeView()
        model = qt.QStandardItemModel(tree)
        tree.setModel(model)
        tree.expandAll()
        collapsed_1 = _property_tree_helper.getPathFromCollapsedNodes(tree)
        _property_tree_helper.collapseNodesFromPaths(tree, collapsed_1)
        collapsed_2 = _property_tree_helper.getPathFromCollapsedNodes(tree)
        assert len(collapsed_1) == 0
        assert collapsed_1 == collapsed_2

    def test_basic(self):
        tree = qt.QTreeView()
        model = qt.QStandardItemModel(tree)
        tree.setModel(model)

        a = qt.QStandardItem("a")
        aa = qt.QStandardItem("aa")
        ab = qt.QStandardItem("ab")
        abb = qt.QStandardItem("abb")
        b = qt.QStandardItem("b")
        model.appendRow(a)
        model.appendRow(b)
        a.appendRow(aa)
        a.appendRow(ab)
        ab.appendRow(abb)

        tree.expandAll()
        tree.setExpanded(ab.index(), False)

        collapsed_1 = _property_tree_helper.getPathFromCollapsedNodes(tree)
        _property_tree_helper.collapseNodesFromPaths(tree, collapsed_1)
        collapsed_2 = _property_tree_helper.getPathFromCollapsedNodes(tree)
        assert len(collapsed_1) == 1
        assert collapsed_1 == collapsed_2
