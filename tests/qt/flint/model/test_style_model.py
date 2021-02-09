"""Testing scan model."""

import pytest
from bliss.flint.model import style_model
from bliss.flint.utils import qsettingsutils
from silx.gui import qt
import tempfile
import shutil


@pytest.fixture
def tmp_settings(xvfb):
    tmpdir = tempfile.mkdtemp(prefix="test-flint")
    defaultFormat = qt.QSettings.IniFormat
    qt.QSettings.setPath(defaultFormat, qt.QSettings.UserScope, tmpdir)
    qt.QSettings.setDefaultFormat(defaultFormat)
    try:
        yield
    finally:
        shutil.rmtree(tmpdir)


def test_read_write_to_settings__empty(tmp_settings):
    style = style_model.Style()
    settings = qt.QSettings()
    qsettingsutils.setNamedTuple(settings, style)
    settings.sync()

    settings = qt.QSettings()
    style2 = qsettingsutils.namedTuple(settings, style_model.Style)
    assert style2 == style


def test_read_nothing_from_settings(tmp_settings):
    settings = qt.QSettings()
    defaultStyle = style_model.Style(colormapLut="viridis")
    style = qsettingsutils.namedTuple(
        settings, style_model.Style, defaultData=defaultStyle
    )
    assert style == defaultStyle


def test_read_write_to_settings__full(tmp_settings):
    style = style_model.Style(
        lineStyle=style_model.LineStyle.SCATTER_SEQUENCE,
        lineColor=(10, 20, 30),
        linePalette=5,
        symbolStyle="o",
        symbolSize=6.6,
        symbolColor=(40, 50, 60),
        colormapLut="viridis",
        fillStyle=style_model.FillStyle.SCATTER_IRREGULAR_GRID,
    )
    settings = qt.QSettings()
    qsettingsutils.setNamedTuple(settings, style)
    settings.sync()

    settings = qt.QSettings()
    style2 = qsettingsutils.namedTuple(settings, style_model.Style)
    assert style2 == style


def test_read_write_to_settings__check_content(tmp_settings):
    style = style_model.Style(
        lineStyle=style_model.LineStyle.SCATTER_SEQUENCE,
        fillStyle=style_model.FillStyle.SCATTER_IRREGULAR_GRID,
    )
    settings = qt.QSettings()
    qsettingsutils.setNamedTuple(settings, style)
    settings.sync()

    settings = qt.QSettings()
    assert settings.value("lineStyle") == style_model.LineStyle.SCATTER_SEQUENCE.code
    assert (
        settings.value("fillStyle") == style_model.FillStyle.SCATTER_IRREGULAR_GRID.code
    )


def test_create_from():
    style = style_model.Style(linePalette=5)
    style2 = style_model.Style(style=style, colormapLut="viridis")
    assert style.colormapLut is None
    assert style2.colormapLut == "viridis"
    assert style.linePalette == style2.linePalette
