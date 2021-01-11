"""Testing Flint startup."""

from bliss.flint import flint
from silx.gui import qt
import typing


def create_qt_mock(mocker):
    """Mock part of qt library"""
    mockQApp = mocker.Mock()
    mockQApplication = mocker.Mock()
    type(mockQApplication).__call__ = mocker.Mock(return_value=mockQApp)
    mockQApplication.instance = mocker.Mock(return_value=None)
    mockQt = mocker.Mock()
    type(mockQt).QApplication = mocker.PropertyMock(return_value=mockQApplication)
    mockQCoreApplication = mocker.Mock()
    type(mockQt).QCoreApplication = mocker.PropertyMock(
        return_value=mockQCoreApplication
    )
    type(mockQt).Qt = mocker.PropertyMock(return_value=qt.Qt)
    mocker.patch("bliss.flint.flint.qt", mockQt)

    assert mockQApplication.instance() is None
    assert mockQApplication.instance() is None

    iconsMock = mocker.Mock()
    mocker.patch("silx.gui.icons", iconsMock)

    class QtStruct(typing.NamedTuple):
        qt: object
        QCoreApplication: object
        qapp: object

    return QtStruct(mockQt, mockQCoreApplication, mockQApp)


def test_shared_context_setup_by_default(mocker):
    """
    Test that QApplication is setup as expected with no specific settings
    """
    mocks = create_qt_mock(mocker)

    settings = qt.QSettings("test", "test")
    settings.clear()

    argv = []
    options = flint.parse_options(argv)
    qapp = flint.initApplication([], options, settings)
    assert qapp is mocks.qapp
    mocks.qt.QCoreApplication.setAttribute.assert_called_with(
        qt.Qt.AA_ShareOpenGLContexts
    )


def test_shared_context_disabled_by_settings(mocker):
    """
    Test that QApplication is setup as expected when settings are setup
    to disable shared context
    """
    mocks = create_qt_mock(mocker)

    settings = qt.QSettings("test", "test")
    settings.clear()
    settings.beginGroup("qapplication")
    settings.setValue("share-opengl-contexts", False)
    settings.endGroup()

    argv = []
    options = flint.parse_options(argv)
    qapp = flint.initApplication([], options, settings)
    assert qapp is mocks.qapp
    mocks.qt.QCoreApplication.setAttribute.assert_not_called()
