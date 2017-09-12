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
    assert interface.init(u"somefile") is None
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


def test_get_detector_from_channel(interface):
    m = interface.handel.xiaDetectorFromDetChan

    def side_effect(channel, alias):
        alias[0:5] = b"name1"
        return 0

    m.side_effect = side_effect
    assert interface.get_detector_from_channel(1) == "name1"
    arg = m.call_args[0][1]
    m.assert_called_once_with(1, arg)
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
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Second test
    assert interface.stop_run(2) is None
    m.assert_called_once_with(2)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_spectrum_length(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_spectrum_length(1) == 10
    m.assert_called_once()
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"mca_length", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_spectrum(interface):
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
    expected = numpy.array(range(10), dtype="uint32")
    diff = interface.get_spectrum(1) == expected
    assert diff.all()
    m.assert_called()
    arg = m.call_args[0][2]
    m.assert_called_with(1, b"mca", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


# Buffer


def test_get_buffer_length(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_buffer_length(1) == 10
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"buffer_len", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_buffer_full(interface):
    with pytest.raises(ValueError) as context:
        interface.get_buffer_full(1, "very wrong")
    assert "very wrong" in str(context.value)

    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 1
        return 0

    m.side_effect = side_effect
    assert interface.get_buffer_full(1, "a") is True
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"buffer_full_a", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_buffer(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        if dtype == b"buffer_len":
            arg[0] = 10
            return 0
        if dtype == b"buffer_a":
            for x in range(10):
                arg[x] = x
            return 0
        assert False

    m.side_effect = side_effect
    expected = numpy.array(range(10), dtype="uint32")
    diff = interface.get_buffer(1, "a") == expected
    assert diff.all()
    m.assert_called()
    arg = m.call_args[0][2]
    m.assert_called_with(1, b"buffer_a", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_buffer_done(interface):
    m = interface.handel.xiaBoardOperation
    m.return_value = 0
    assert interface.buffer_done(1, "b") is None
    m.assert_called_with(1, b"buffer_done", b"b")
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


# System


def test_load_system(interface):
    m = interface.handel.xiaLoadSystem
    m.return_value = 0
    assert interface.load_system("somefile") is None
    m.assert_called_once_with(b"handel_ini", b"somefile")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_save_system(interface):
    m = interface.handel.xiaSaveSystem
    m.return_value = 0
    assert interface.save_system("somefile") is None
    m.assert_called_once_with(b"handel_ini", b"somefile")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_start_system(interface):
    m = interface.handel.xiaStartSystem
    m.return_value = 0
    assert interface.start_system() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


# Logging


def test_enable_log_output(interface):
    m = interface.handel.xiaEnableLogOutput
    m.return_value = 0
    assert interface.enable_log_output() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_disable_log_output(interface):
    m = interface.handel.xiaSuppressLogOutput
    m.return_value = 0
    assert interface.disable_log_output() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_set_log_level(interface):
    m = interface.handel.xiaSetLogLevel
    m.return_value = 0
    assert interface.set_log_level(3) is None
    m.assert_called_once_with(3)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_set_log_output(interface):
    m = interface.handel.xiaSetLogOutput
    m.return_value = 0
    assert interface.set_log_output("somefile") is None
    m.assert_called_once_with(b"somefile")
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_close_log(interface):
    m = interface.handel.xiaCloseLog
    m.return_value = 0
    assert interface.close_log() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


# Modules


def test_get_num_modules(interface):
    m = interface.handel.xiaGetNumModules

    def side_effect(arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_num_modules() == 10
    arg = m.call_args[0][0]
    m.assert_called_once_with(arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_modules(interface):
    m1 = interface.handel.xiaGetNumModules
    m2 = interface.handel.xiaGetModules

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
    assert interface.get_modules() == expected
    m2.assert_called_once()
    arg = m2.call_args[0][0]
    m2.assert_called_once_with(arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_module_from_channel(interface):
    m = interface.handel.xiaModuleFromDetChan

    def side_effect(channel, alias):
        alias[0:5] = b"name1"
        return 0

    m.side_effect = side_effect
    assert interface.get_module_from_channel(1) == "name1"
    arg = m.call_args[0][1]
    m.assert_called_once_with(1, arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_module_type(interface):
    m = interface.handel.xiaGetModuleItem

    def side_effect(a, b, c):
        c[0:7] = b"mercury"
        return 0

    m.side_effect = side_effect
    assert interface.get_module_type("module1") == "mercury"
    arg = m.call_args[0][2]
    m.assert_called_once_with(b"module1", b"module_type", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_module_interface(interface):
    m = interface.handel.xiaGetModuleItem

    def side_effect(a, b, c):
        c[0:4] = b"usb2"
        return 0

    m.side_effect = side_effect
    assert interface.get_module_interface("module1") == "usb2"
    arg = m.call_args[0][2]
    m.assert_called_once_with(b"module1", b"interface", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_module_number_of_channels(interface):
    m = interface.handel.xiaGetModuleItem

    def side_effect(a, b, c):
        c[0] = 4
        return 0

    m.side_effect = side_effect
    assert interface.get_module_number_of_channels("module1") == 4
    arg = m.call_args[0][2]
    m.assert_called_once_with(b"module1", b"number_of_channels", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_module_channel_at(interface):
    m = interface.handel.xiaGetModuleItem

    def side_effect(a, b, c):
        c[0] = 3
        return 0

    m.side_effect = side_effect
    assert interface.get_module_channel_at("module1", 2) == 3
    arg = m.call_args[0][2]
    m.assert_called_once_with(b"module1", b"channel2_alias", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_module_channels(interface):
    m = interface.handel.xiaGetModuleItem
    results = [3, 2, 1, 0, 4]

    def side_effect(a, b, c):
        c[0] = results.pop()
        return 0

    m.side_effect = side_effect
    assert interface.get_module_channels("module1") == (0, 1, 2, 3)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_grouped_channels(interface):
    m1 = interface.handel.xiaGetNumModules
    m2 = interface.handel.xiaGetModules
    m3 = interface.handel.xiaGetModuleItem
    results = [3, 2, 1, 0, 4, 7, 6, 5, 4, 4]

    def side_effect_1(arg):
        arg[0] = 2
        return 0

    def side_effect_2(lst):
        lst[0][0:5] = b"name1"
        lst[1][0:5] = b"name2"
        return 0

    def side_effect_3(a, b, c):
        c[0] = results.pop()
        return 0

    m1.side_effect = side_effect_1
    m2.side_effect = side_effect_2
    m3.side_effect = side_effect_3
    assert interface.get_grouped_channels() == ((4, 5, 6, 7), (0, 1, 2, 3))
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_channels(interface):
    m1 = interface.handel.xiaGetNumModules
    m2 = interface.handel.xiaGetModules
    m3 = interface.handel.xiaGetModuleItem
    results = [3, 2, 1, 0, 4, 7, 6, 5, 4, 4]

    def side_effect_1(arg):
        arg[0] = 2
        return 0

    def side_effect_2(lst):
        lst[0][0:5] = b"name1"
        lst[1][0:5] = b"name2"
        return 0

    def side_effect_3(a, b, c):
        c[0] = results.pop()
        return 0

    m1.side_effect = side_effect_1
    m2.side_effect = side_effect_2
    m3.side_effect = side_effect_3
    assert interface.get_channels() == (0, 1, 2, 3, 4, 5, 6, 7)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


# Parameters


def test_get_acquistion_value(interface):
    m = interface.handel.xiaGetAcquisitionValues

    def side_effect(a, b, c):
        c[0] = 2.3
        return 0

    m.side_effect = side_effect
    assert interface.get_acquisition_value("test", channel=1) == 2.3
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"test", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_set_acquisition_value(interface):
    m = interface.handel.xiaSetAcquisitionValues
    m.return_value = 0

    # Single channel
    assert interface.set_acquisition_value("test", 2.3, channel=1) is None
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"test", arg)
    assert arg[0] == 2.3

    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    m.reset_mock()

    # All channels
    assert interface.set_acquisition_value("test", 2.3) is None
    arg = m.call_args[0][2]
    m.assert_called_once_with(-1, b"test", arg)
    assert arg[0] == 2.3


def test_remove_acquisition_value(interface):
    m = interface.handel.xiaRemoveAcquisitionValues
    m.return_value = 0

    # Single channel
    assert interface.remove_acquisition_value("test", channel=1) is None
    m.assert_called_once_with(1, b"test")

    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    m.reset_mock()

    # Multiple channels
    assert interface.remove_acquisition_value("test") is None
    m.assert_called_once_with(-1, b"test")


def test_apply_acquisition_values(interface):
    m = interface.handel.xiaBoardOperation
    m.return_value = 0

    # Single channel
    assert interface.apply_acquisition_values(channel=1) is None
    dummy = m.call_args[0][2]
    m.assert_called_once_with(1, b"apply", dummy)

    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)
    m.reset_mock()

    # Multiple channel
    with mock.patch(
        "bliss.controllers.mca.handel.interface.get_grouped_channels"
    ) as m2:
        m2.return_value = ((0,),)
        assert interface.apply_acquisition_values() is None
        dummy = m.call_args[0][2]
        m.assert_called_once_with(0, b"apply", dummy)


# Debugging


def test_get_handel_version(interface):
    m = interface.handel.xiaGetVersionInfo

    def side_effect(a, b, c, d):
        d[0], c[0], b[0], a[0] = b"v", 1, 2, 3

    m.side_effect = side_effect
    assert interface.get_handel_version() == (1, 2, 3)
    m.assert_called_once()
    # xiaGetVersionInfo does not return an error code


# Files


def test_get_config_files(interface):
    assert interface.get_config_files(".") == ["scripts/handel/mercury.ini"]
    assert interface.get_config_files(b".") == [b"scripts/handel/mercury.ini"]


def test_get_config(interface):
    # Using string paths
    filename = interface.get_config_files(".")[0]
    conf = interface.get_config(".", filename)
    assert conf["detector definitions"][0]["alias"] == "detector1"
    with pytest.raises(IOError):
        interface.get_config(".", "i_dont_exist.ini")

    # Using bytestring paths
    filename = interface.get_config_files(b".")[0]
    conf = interface.get_config(b".", filename)
    assert conf["detector definitions"][0]["alias"] == "detector1"
    with pytest.raises(IOError):
        interface.get_config(b".", b"i_dont_exist.ini")
