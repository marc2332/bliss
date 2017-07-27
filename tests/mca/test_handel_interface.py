import pytest
import mock


@pytest.fixture
def interface():
    with mock.patch("cffi.FFI.dlopen") as dlopen:
        from bliss.controllers.mca.handel import interface

        interface.handel = dlopen.return_value
        yield interface


def test_init(interface):
    m = interface.handel.xiaInit
    m.return_value = 0
    assert interface.init("somefile") is None
    m.assert_called_with("somefile")


def test_init_handel(interface):
    m = interface.handel.xiaInitHandel
    m.return_value = 0
    assert interface.init_handel() is None
    m.assert_called_with()


def test_new_detector(interface):
    m = interface.handel.xiaNewDetector
    m.return_value = 0
    assert interface.new_detector("somealias") is None
    m.assert_called_with("somealias")
