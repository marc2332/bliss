import pytest
import numpy
import mock


@pytest.fixture
def interface():
    with mock.patch("cffi.FFI.dlopen") as dlopen:
        with mock.patch("bliss.controllers.mca.handel.interface.check_error"):
            from bliss.controllers.mca.handel import interface

            interface.handel = dlopen.return_value
            yield interface


# Initializing handel


def test_init(interface):
    m = interface.handel.xiaInit
    m.return_value = 0
    assert interface.init("somefile") is None
    m.assert_called_once_with(b"somefile")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Should work with bytes too
    assert interface.init(b"somefile") is None
    m.assert_called_once_with(b"somefile")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_init_handel(interface):
    m = interface.handel.xiaInitHandel
    m.return_value = 0
    assert interface.init_handel() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_exit(interface):
    m = interface.handel.xiaExit
    m.return_value = 0
    assert interface.exit() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


# Detectors


def test_new_detector(interface):
    m = interface.handel.xiaNewDetector
    m.return_value = 0
    assert interface.new_detector("somealias") is None
    m.assert_called_once_with(b"somealias")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_num_detectors(interface):
    m = interface.handel.xiaGetNumDetectors

    def side_effect(arg):
        arg[0] = 3
        return 0

    m.side_effect = side_effect
    assert interface.get_num_detectors() == 3
    m.assert_called_once()
    arg = m.call_args[0][0]
    m.assert_called_once_with(arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_detectors(interface):
    m1 = interface.handel.xiaGetNumDetectors
    m2 = interface.handel.xiaGetDetectors

    def side_effect_1(arg):
        arg[0] = 3
        return 0

    def side_effect_2(lst):
        lst[0][0:5] = b"name1"
        lst[1][0:5] = b"name2"
        lst[2][0:5] = b"name3"
        return 0

    m1.side_effect = side_effect_1
    m2.side_effect = side_effect_2
    expected = "name1", "name2", "name3"
    assert interface.get_detectors() == expected
    m2.assert_called_once()
    arg = m2.call_args[0][0]
    m2.assert_called_once_with(arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


# Run control


def test_start_run(interface):
    m = interface.handel.xiaStartRun
    m.return_value = 0
    # First test
    assert interface.start_run(1) is None
    m.assert_called_once_with(1, False)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Second test
    assert interface.start_run(2, True) is None
    m.assert_called_once_with(2, True)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_stop_run(interface):
    # Init
    m = interface.handel.xiaStopRun
    m.return_value = 0
    # First test
    assert interface.stop_run(1) is None
    m.assert_called_once_with(1)
    interface.check_error.assert_called_once_with(0)
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Second test
    assert interface.stop_run(2) is None
    m.assert_called_once_with(2)
    interface.check_error.assert_called_once_with(0)


def test_get_run_data_length(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_run_data_length(1) == 10
    m.assert_called_once()
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"mca_length", arg)
    interface.check_error.assert_called_once_with(0)


def test_get_run_data(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        if dtype == b"mca_length":
            arg[0] = 10
            return 0
        if dtype == b"mca":
            for x in range(10):
                arg[x] = x
            return 0
        assert False

    m.side_effect = side_effect
    expected = numpy.array(range(10), dtype="uint")
    diff = interface.get_run_data(1) == expected
    assert diff.all()
    m.assert_called()
    arg = m.call_args[0][2]
    m.assert_called_with(1, b"mca", arg)
    interface.check_error.assert_called_with(0)


# System


def test_load_system(interface):
    m = interface.handel.xiaLoadSystem
    m.return_value = 0
    assert interface.load_system("somefile") is None
    m.assert_called_once_with(b"handel_ini", b"somefile")
    interface.check_error.assert_called_once_with(0)


def test_save_system(interface):
    m = interface.handel.xiaSaveSystem
    m.return_value = 0
    assert interface.save_system("somefile") is None
    m.assert_called_once_with(b"handel_ini", b"somefile")
    interface.check_error.assert_called_once_with(0)


def test_start_system(interface):
    m = interface.handel.xiaStartSystem
    m.return_value = 0
    assert interface.start_system() is None
    m.assert_called_once_with()
    interface.check_error.assert_called_once_with(0)


# Logging


def test_enable_log_output(interface):
    m = interface.handel.xiaEnableLogOutput
    m.return_value = 0
    assert interface.enable_log_output() is None
    m.assert_called_once_with()
    interface.check_error.assert_called_once_with(0)


def test_disable_log_output(interface):
    m = interface.handel.xiaSuppressLogOutput
    m.return_value = 0
    assert interface.disable_log_output() is None
    m.assert_called_once_with()
    interface.check_error.assert_called_once_with(0)


def test_set_log_level(interface):
    m = interface.handel.xiaSetLogLevel
    m.return_value = 0
    assert interface.set_log_level(3) is None
    m.assert_called_once_with(3)
    interface.check_error.assert_called_once_with(0)


def test_set_log_output(interface):
    m = interface.handel.xiaSetLogOutput
    m.return_value = 0
    assert interface.set_log_output("somefile") is None
    m.assert_called_once_with(b"somefile")
    interface.check_error.assert_called_once_with(0)


def test_close_log(interface):
    m = interface.handel.xiaCloseLog
    m.return_value = 0
    assert interface.close_log() is None
    m.assert_called_once_with()
    interface.check_error.assert_called_once_with(0)


# Parameters


def test_set_acquisition_value(interface):
    m = interface.handel.xiaSetAcquisitionValues
    m.return_value = 0
    assert interface.set_acquisition_value(1, "test", 2.3) is None
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"test", arg)
    assert arg[0] == 2.3
    interface.check_error.assert_called_once_with(0)


def test_get_acquistion_value(interface):
    m = interface.handel.xiaGetAcquisitionValues

    def side_effect(a, b, c):
        c[0] = 2.3
        return 0

    m.side_effect = side_effect
    assert interface.get_acquisition_value(1, "test") == 2.3
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"test", arg)
    interface.check_error.assert_called_once_with(0)


# Debugging


def test_get_handel_version(interface):
    m = interface.handel.xiaGetVersionInfo

    def side_effect(a, b, c, d):
        d[0], c[0], b[0], a[0] = b"v", 1, 2, 3

    m.side_effect = side_effect
    assert interface.get_handel_version() == (1, 2, 3)
    m.assert_called_once()
