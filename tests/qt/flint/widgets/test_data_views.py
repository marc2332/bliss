import pytest
from silx.gui import qt
from bliss.flint.widgets import delegates
from bliss.flint.widgets import data_views


class ViewDelegate1(qt.QStyledItemDelegate):
    def initStyleOption(self, option: qt.QStyleOptionViewItem, index: qt.QModelIndex):
        text = str(index.data(delegates.ObjectRole))
        option.text = text + "!!"

        color = qt.QColor()
        color.setNamedColor(text)
        pixmap = qt.QPixmap(16, 16)
        pixmap.fill(color)
        icon = qt.QIcon(pixmap)
        option.icon = icon
        option.features |= qt.QStyleOptionViewItem.HasDecoration
        option.decorationSize = qt.QSize(16, 16)


class ViewDelegate2(qt.QStyledItemDelegate):
    def initStyleOption(self, option: qt.QStyleOptionViewItem, index: qt.QModelIndex):
        # scanItem = index.data(delegates.ObjectRole)
        text = str(index.data())
        option.text = text + "?"


class ViewDelegate3(qt.QStyledItemDelegate):
    EDITOR_ALWAYS_OPEN = True

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(ViewDelegate3, self).createEditor(parent, option, index)
        editor = qt.QLineEdit(parent=parent)
        editor.destroyed.connect(lambda: print("destroyed"))
        editor.textChanged.connect(self.__changed)
        return editor

    def setEditorData(self, editor: qt.QLineEdit, index):
        value = index.data(delegates.ObjectRole)
        editor.blockSignals(True)
        editor.setText(value)
        editor.blockSignals(False)

    def __changed(self):
        sender = self.sender()
        self.commitData.emit(sender)

    def setModelData(self, editor: qt.QLineEdit, model, index):
        pass


@pytest.fixture
def tree():
    tree = data_views.DataTreeView()
    tree.setColumn(0, "col1", delegate=ViewDelegate1)
    tree.setColumn(1, "col2", delegate=ViewDelegate2)
    tree.setColumn(2, "col3", delegate=ViewDelegate3)
    tree.setDisplayedColumns([0, 2])
    window = qt.QMainWindow()
    window.setCentralWidget(tree)
    window.setVisible(True)
    yield tree
    window.deleteLater()


@pytest.fixture
def table():
    table = data_views.VDataTableView()
    table.setColumn(0, "col1", delegate=ViewDelegate1)
    table.setColumn(1, "col2", delegate=ViewDelegate2)
    table.setColumn(2, "col3", delegate=ViewDelegate3)
    table.setDisplayedColumns([0, 2])
    window = qt.QMainWindow()
    window.setCentralWidget(table)
    window.setVisible(True)
    yield table
    window.deleteLater()


def test_tree_view(qapp, tree):
    """
    Create a tree with a model

    Make sure the amount of columns, cells and editors are properly displayed
    """
    tree.setDisplayedColumns([0, 2])
    item = qt.QStandardItem("blue")
    item2 = qt.QStandardItem("red")
    for i in [item, item2]:
        i.setData(i.text(), role=delegates.ObjectRole)
    model = qt.QStandardItemModel()
    root = model.invisibleRootItem()
    root.appendRow(item)
    item.appendRow(item2)

    tree.setSourceModel(model)
    qapp.processEvents()

    header = tree.header()
    assert header.hiddenSectionCount() == 1

    editor = tree.indexWidget(item.index(), column=2)
    assert isinstance(editor, qt.QLineEdit)

    tree.expand(item.index())
    editor = tree.indexWidget(item2.index(), column=2)
    assert isinstance(editor, qt.QLineEdit)


def test_tree_view__reset_model(qapp, tree):
    """
    Create a tree without model, set a new one

    Make sure the amount of columns, cells and editors are properly displayed
    """
    tree.setDisplayedColumns([0, 2])
    qapp.processEvents()

    item = qt.QStandardItem("blue")
    item2 = qt.QStandardItem("red")
    for i in [item, item2]:
        i.setData(i.text(), role=delegates.ObjectRole)
    model = qt.QStandardItemModel()
    root = model.invisibleRootItem()
    root.appendRow(item)
    item.appendRow(item2)
    tree.setSourceModel(model)
    qapp.processEvents()

    header = tree.header()
    assert header.hiddenSectionCount() == 1

    editor = tree.indexWidget(item.index(), column=2)
    assert isinstance(editor, qt.QLineEdit)

    tree.expand(item.index())
    editor = tree.indexWidget(item2.index(), column=2)
    assert isinstance(editor, qt.QLineEdit)


def test_table_view(qapp, table):
    """
    Create a table with a model

    Make sure the amount of columns, cells and editors are properly displayed
    """
    model = data_views.ObjectListModel()
    model.setObjectList(["blue", "red"])
    table.setSourceModel(model)
    qapp.processEvents()

    header = table.horizontalHeader()
    assert header.hiddenSectionCount() == 1

    editor = table.indexWidget(model.index(0, 0), column=2)
    assert isinstance(editor, qt.QLineEdit)

    editor = table.indexWidget(model.index(1, 0), column=2)
    assert isinstance(editor, qt.QLineEdit)


def test_table_view__reset_model(qapp, table):
    """
    Create a table without model, set a new one

    Make sure the amount of columns, cells and editors are properly displayed
    """
    table.setDisplayedColumns([0, 2])
    qapp.processEvents()

    model = data_views.ObjectListModel()
    model.setObjectList(["blue", "red"])
    table.setSourceModel(model)
    qapp.processEvents()

    header = table.horizontalHeader()
    assert header.hiddenSectionCount() == 1

    editor = table.indexWidget(model.index(0, 0), column=2)
    assert isinstance(editor, qt.QLineEdit)

    editor = table.indexWidget(model.index(1, 0), column=2)
    assert isinstance(editor, qt.QLineEdit)
