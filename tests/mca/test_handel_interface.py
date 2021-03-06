from unittest import mock
import numpy
import pytest

from bliss.controllers.mca.handel.stats import Stats
from bliss.controllers.mca.handel.error import HandelError


@pytest.fixture
def interface():
    with mock.patch("cffi.FFI.dlopen") as dlopen:
        with mock.patch("bliss.controllers.mca.handel.interface.check_error"):
            from bliss.controllers.mca.handel import interface

            interface.handel = dlopen.return_value
            yield interface


# Initializing handel


def test_init(beacon, interface):
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


def test_init_handel(beacon, interface):
    m = interface.handel.xiaInitHandel
    m.return_value = 0
    assert interface.init_handel("simu1") is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called()


def test_exit(interface):
    m = interface.handel.xiaExit
    m.return_value = 0
    assert interface.exit_handel() is None
    m.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


# Detectors


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


#    interface.check_error.assert_called_once_with(0)


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
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Third test
    assert interface.start_run() is None
    m.assert_called_once_with(-1, False)
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
    # Reset
    m.reset_mock()
    interface.check_error.reset_mock()
    # Second test
    assert interface.stop_run() is None
    m.assert_called_once_with(-1)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_channel_realtime(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 1.23
        return 0

    m.side_effect = side_effect
    assert interface.get_channel_realtime(1) == 1.23
    m.assert_called_once()
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"realtime", arg)
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


def test_get_spectrums(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_channels") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.get_spectrum") as m2:
            m1.return_value = [0, 1]
            # First test
            spectrums = [[0, 1, 2], [2, 3, 4]]
            m2.side_effect = lambda x: spectrums[x]
            expected = {0: [0, 1, 2], 1: [2, 3, 4]}
            assert interface.get_spectrums() == expected
            m1.assert_called_once_with()
            m2.assert_called_with(1)


def test_is_channel_running(interface):
    # First test
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 1
        return 0

    m.side_effect = side_effect
    assert interface.is_channel_running(2) is True
    arg = m.call_args[0][2]
    m.assert_called_once_with(2, b"run_active", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)

    # Second test
    m.reset_mock()
    interface.check_error.reset_mock()

    def side_effect(channel, dtype, arg):
        arg[0] = 2  # 2 is actually a valid value for a non-running channel
        return 0

    m.side_effect = side_effect
    assert interface.is_channel_running(2) is False
    arg = m.call_args[0][2]
    m.assert_called_once_with(2, b"run_active", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_is_running(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_channels") as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.is_channel_running"
        ) as m2:
            m1.return_value = [0, 1, 2]
            # First test
            m2.side_effect = lambda x: x == 1
            assert interface.is_running() is True
            m1.assert_called_once_with()
            m2.assert_called_with(1)
            # Second test
            m2.side_effect = lambda x: False
            assert interface.is_running() is False


# Statistics


def test_get_module_statistics(interface, caplog):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[3 * 9 : 4 * 9] = raw
        return 0

    raw = [
        1.00758784,  # realtime
        0.98603936,  # trigger_livetime
        255.0,  # energy_livetime
        3088.0,  # triggers
        2742.0,  # events    # without under/over flows
        3131.720827046904,  # icr
        2724.3282332585513,  # ocr
        1.0,  # underflows ??
        2.0,  # overflows ??
    ]

    expected = {
        8: Stats(
            1.00758784,  # realtime
            0.98603936,  # trigger_livetime
            0.8755569705699482,  # energy_livetime
            3088,  # triggers
            2742,  # events
            3131.720827046904,  # icr
            2721.350825353351,  # ocr
            0.13103658479051494,  # deadtime
        )
    }

    m.side_effect = side_effect
    with mock.patch("bliss.controllers.mca.handel.interface.get_module_channels") as m2:
        with mock.patch("bliss.controllers.mca.handel.interface.get_module_type") as m3:
            with mock.patch(
                "bliss.controllers.mca.handel.interface.get_spectrum"
            ) as m4:
                m2.return_value = [-1, -1, -1, 8]
                m3.return_value = "falconxn"
                m4.side_effect = HandelError(12, "hello")

                # First test
                assert interface.get_module_statistics("module3") == expected
                m2.assert_called_once_with("module3")
                arg = m.call_args[0][2]
                m.assert_called_once_with(8, b"module_statistics_2", arg)
                m4.assert_called_once_with(8)

                # Second test
                raw[5] = 4.56  # ICR inconsistency
                raw[6] = 1.23  # OCR inconsistency

                interface.get_module_statistics("module3")
                assert "ICR buffer inconsistency: 4.56 != 3131.7208" in caplog.text
                assert "OCR buffer inconsistency: 1.23 != 2724.3282" in caplog.text

    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_statistics(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_modules") as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.get_module_statistics"
        ) as m2:
            m1.return_value = ["module1", "module2"]
            stats = {
                "module1": {0: "some", 1: "stats"},
                "module2": {2: "and", 3: "some more"},
            }
            m2.side_effect = lambda x: stats[x]
            expected = {0: "some", 1: "stats", 2: "and", 3: "some more"}
            assert interface.get_statistics() == expected
            m1.assert_called_once_with()
            m2.assert_called_with("module2")


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


def test_is_buffer_full(interface):
    with pytest.raises(ValueError) as context:
        interface.is_buffer_full(1, "very wrong")
    assert "very wrong" in str(context.value)

    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 1
        return 0

    m.side_effect = side_effect
    assert interface.is_buffer_full(1, "a") is True
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"buffer_full_a", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_is_buffer_overrun(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 1
        return 0

    m.side_effect = side_effect
    assert interface.is_buffer_overrun(1) is True
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"buffer_overrun", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_get_raw_buffer(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        if dtype == b"buffer_len":
            arg[0] = 5
            return 0
        if dtype == b"buffer_a":
            arg[0:5] = buff
            return 0
        assert False

    # First test
    buff = range(1, 6)
    m.side_effect = side_effect
    expected = numpy.array(range(1, 6), dtype="uint32")
    assert numpy.array_equal(interface.get_raw_buffer(1, "a")[::2], expected)
    m.assert_called()
    arg = m.call_args[0][2]
    m.assert_called_with(1, b"buffer_a", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)

    # Second test
    buff = [0] * 5
    with pytest.raises(RuntimeError) as ctx:
        interface.get_raw_buffer(1, "a")
    assert "The buffer a associated with channel 1 is empty" in str(ctx.value)


def test_get_buffer_data(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_raw_buffer") as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.parse_mapping_buffer"
        ) as m2:
            assert interface.get_buffer_data(3, "b") is m2.return_value
            m1.assert_called_once_with(3, "b")
            m2.assert_called_once_with(m1.return_value)


def test_get_buffer_current_pixel(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_buffer_current_pixel(1) == 10
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"current_pixel", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


def test_set_buffer_done(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.is_channel_running") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.is_buffer_full") as m2:
            m = interface.handel.xiaBoardOperation
            m.return_value = 0
            m1.return_value = True
            m2.return_value = True
            assert interface.set_buffer_done(1, "b") is True
            m.assert_called_with(1, b"buffer_done", b"b")
            m1.assert_called_once_with(1)
            m2.assert_called_once_with(1, b"a")
            # Make sure errors have been checked
            interface.check_error.assert_called_once_with(0)


# Synchronized run


def test_set_maximum_pixels_per_buffer(interface):
    with mock.patch(
        "bliss.controllers.mca.handel.interface.set_acquisition_value"
    ) as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.get_acquisition_value"
        ) as m2:
            with mock.patch(
                "bliss.controllers.mca.handel.interface.get_master_channels"
            ) as m3:
                m1.return_value = None
                m2.side_effect = lambda x, y: 400 if y == 7 else 100
                m3.return_value = [0, 3, 7]
                assert interface.set_maximum_pixels_per_buffer() is None
                assert m1.call_args_list == [
                    (("num_map_pixels_per_buffer", -1),),
                    (("num_map_pixels_per_buffer", 100),),
                ]
                assert m2.call_args_list == [
                    (("num_map_pixels_per_buffer", 0),),
                    (("num_map_pixels_per_buffer", 3),),
                    (("num_map_pixels_per_buffer", 7),),
                ]
                m3.assert_called_once_with()


def test_any_buffer_overrun(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_master_channels") as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.is_buffer_overrun"
        ) as m2:
            m1.return_value = [0, 4]
            m2.side_effect = lambda x: x != 0
            assert interface.any_buffer_overrun() is True
            m1.assert_called_once_with()
            m2.assert_called_with(4)


def test_all_buffer_full(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_master_channels") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.is_buffer_full") as m2:
            m1.return_value = [0, 4]
            m2.return_value = True
            assert interface.all_buffer_full("b") is True
            m1.assert_called_once_with()
            m2.assert_called_with(4, "b")


def test_set_all_buffer_done(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_master_channels") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.set_buffer_done") as m2:
            m1.return_value = [0, 4]
            m2.side_effect = lambda x, y: x == 0
            assert interface.set_all_buffer_done("b") is True
            m1.assert_called_once_with()
            m2.assert_called_with(4, "b")


def test_get_current_pixel(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_master_channels") as m1:
        with mock.patch(
            "bliss.controllers.mca.handel.interface.get_buffer_current_pixel"
        ) as m2:
            m1.return_value = [0, 4]
            m2.side_effect = lambda x: 1 if x == 0 else 2
            assert interface.get_current_pixel() == 2
            m1.assert_called_once_with()
            m2.assert_called_with(4)


def test_get_all_buffer_data(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_master_channels") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.get_buffer_data") as m2:
            m1.return_value = [0, 4]
            first = {11: {0: "spectrum1"}}, {11: {0: "stats1"}}
            second = {11: {4: "spectrum2"}}, {11: {4: "stats2"}}
            expected = (
                {11: {0: "spectrum1", 4: "spectrum2"}},
                {11: {0: "stats1", 4: "stats2"}},
            )
            m2.side_effect = lambda x, y: first if x == 0 else second
            assert interface.get_all_buffer_data("b") == expected
            m1.assert_called_once_with()
            m2.assert_called_with(4, "b")


def test_synchronized_poll_data(interface):
    with mock.patch.multiple(
        "bliss.controllers.mca.handel.interface",
        get_current_pixel=mock.DEFAULT,
        any_buffer_overrun=mock.DEFAULT,
        all_buffer_full=mock.DEFAULT,
        get_all_buffer_data=mock.DEFAULT,
        set_all_buffer_done=mock.DEFAULT,
    ) as ms:

        # First hard overrun
        ms["any_buffer_overrun"].return_value = True
        _acq_number = 0
        with pytest.raises(RuntimeError) as ctx:
            interface.synchronized_poll_data(_acq_number)
        assert "Buffer overrun (hwd)!" in str(ctx.value)
        ms["get_current_pixel"].assert_called_once_with()
        ms["any_buffer_overrun"].assert_called_once_with()
        assert ms["all_buffer_full"].call_args_list == [(("a",),), (("b",),)]
        ms["get_all_buffer_data"].assert_not_called()
        ms["set_all_buffer_done"].assert_not_called()

        # Reset
        for m in ms.values():
            m.reset_mock()

        # Data not ready
        ms["get_current_pixel"].return_value = 10
        ms["any_buffer_overrun"].return_value = False
        ms["all_buffer_full"].return_value = False
        assert interface.synchronized_poll_data(_acq_number) == (10, {}, {})
        ms["get_current_pixel"].assert_called_once_with()
        ms["any_buffer_overrun"].assert_called_once_with()
        assert ms["all_buffer_full"].call_args_list == [(("a",),), (("b",),)]
        ms["get_all_buffer_data"].assert_not_called()
        ms["set_all_buffer_done"].assert_not_called()

        # Reset
        for m in ms.values():
            m.reset_mock()

        # Soft overrun
        ms["get_current_pixel"].return_value = 20
        ms["any_buffer_overrun"].return_value = False
        ms["all_buffer_full"].side_effect = lambda x: x == "a"
        ms["get_all_buffer_data"].return_value = "spectrums", "stats"
        ms["set_all_buffer_done"].return_value = True
        with pytest.raises(RuntimeError) as ctx:
            interface.synchronized_poll_data(_acq_number)
        assert "Buffer overrun (soft)!" in str(ctx.value)
        ms["get_current_pixel"].assert_called_once_with()
        ms["any_buffer_overrun"].assert_called_once_with()
        assert ms["all_buffer_full"].call_args_list == [(("a",),), (("b",),)]
        ms["get_all_buffer_data"].assert_called_once_with("a")
        ms["set_all_buffer_done"].assert_called_once_with("a")

        # Reset
        for m in ms.values():
            m.reset_mock()

        # Data ready
        ms["get_current_pixel"].return_value = 20
        ms["any_buffer_overrun"].return_value = False
        ms["all_buffer_full"].side_effect = lambda x: x == "b"
        ms["get_all_buffer_data"].return_value = "spectrums", "stats"
        ms["set_all_buffer_done"].return_value = False
        assert interface.synchronized_poll_data(_acq_number) == (
            20,
            "spectrums",
            "stats",
        )
        ms["get_current_pixel"].assert_called_once_with()
        ms["any_buffer_overrun"].assert_called_once_with()
        assert ms["all_buffer_full"].call_args_list == [(("a",),), (("b",),)]
        ms["get_all_buffer_data"].assert_called_once_with("b")
        ms["set_all_buffer_done"].assert_called_once_with("b")


# Baseline


def test_get_baseline_length(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        arg[0] = 10
        return 0

    m.side_effect = side_effect
    assert interface.get_baseline_length(1) == 10
    m.assert_called_once()
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"baseline_length", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)


def test_get_baseline(interface):
    m = interface.handel.xiaGetRunData

    def side_effect(channel, dtype, arg):
        if dtype == b"baseline_length":
            arg[0] = 10
            return 0
        if dtype == b"baseline":
            for x in range(10):
                arg[x] = x
            return 0
        assert False

    m.side_effect = side_effect
    expected = numpy.array(range(10), dtype="uint32")
    diff = interface.get_baseline(1) == expected
    assert diff.all()
    m.assert_called()
    arg = m.call_args[0][2]
    m.assert_called_with(1, b"baseline", arg)
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

    # All channels
    m.reset_mock()
    interface.check_error.reset_mock()
    with mock.patch("bliss.controllers.mca.handel.interface.get_modules") as m2:
        m2.return_value = ["module1", "module2"]
        assert interface.get_module_type() == "mercury"
    arg = m.call_args[0][2]
    m.assert_called_with(b"module2", b"module_type", arg)
    m2.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)

    def side_effect(a, b, c):
        c[0:7] = b"mercury" if a == b"module1" else b"xmap\x00\x00\x00"
        return 0

    # All channels with error
    m.reset_mock()
    interface.check_error.reset_mock()
    m.side_effect = side_effect
    with mock.patch("bliss.controllers.mca.handel.interface.get_modules") as m2:
        m2.return_value = ["module1", "module2"]
        with pytest.raises(ValueError):
            interface.get_module_type()
    arg = m.call_args[0][2]
    m.assert_called_with(b"module2", b"module_type", arg)
    m2.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


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


def test_get_master_channels(interface):
    with mock.patch(
        "bliss.controllers.mca.handel.interface.get_grouped_channels"
    ) as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.get_module_type") as m2:
            m1.return_value = [(0, 1, 2, 3), (-1, 5, 6, 7)]
            m2.return_value = "notfalconx"
            assert interface.get_master_channels() == (0, 5)
            m1.assert_called_once_with()
    with mock.patch("bliss.controllers.mca.handel.interface.get_channels") as m1:
        with mock.patch("bliss.controllers.mca.handel.interface.get_module_type") as m2:
            m1.return_value = (0, 1, 2)
            m2.return_value = "falconxn"
            assert interface.get_master_channels() == (0, 1, 2)
            m1.assert_called_once_with()


def test_get_trigger_channels(interface):
    with mock.patch("bliss.controllers.mca.handel.interface.get_grouped_channels") as m:
        m.return_value = [(0, 1, 2, 3), (-1, 5, 6, 7)]
        assert interface.get_trigger_channels() == (0,)
        m.assert_called_once_with()


# Parameters


def test_get_acquistion_value(interface):
    m = interface.handel.xiaGetAcquisitionValues

    def side_effect(a, b, c):
        c[0] = 2.3
        return 0

    # Single channel
    m.side_effect = side_effect
    assert interface.get_acquisition_value("test", channel=1) == 2.3
    arg = m.call_args[0][2]
    m.assert_called_once_with(1, b"test", arg)
    # Make sure errors have been checked
    interface.check_error.assert_called_once_with(0)

    # All channels
    m.reset_mock()
    interface.check_error.reset_mock()
    with mock.patch("bliss.controllers.mca.handel.interface.get_channels") as m2:
        m2.return_value = [0, 1, 2]
        assert interface.get_acquisition_value("test") == 2.3
    arg = m.call_args[0][2]
    m.assert_called_with(2, b"test", arg)
    m2.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)

    def side_effect(a, b, c):
        c[0] = a  # Channel number
        return 0

    # All channels with error
    m.reset_mock()
    interface.check_error.reset_mock()
    m.side_effect = side_effect
    with mock.patch("bliss.controllers.mca.handel.interface.get_channels") as m2:
        m2.return_value = [0, 1, 2]
        with pytest.raises(ValueError):
            interface.get_acquisition_value("test")
    arg = m.call_args[0][2]
    m.assert_called_with(2, b"test", arg)
    m2.assert_called_once_with()
    # Make sure errors have been checked
    interface.check_error.assert_called_with(0)


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
        with mock.patch("bliss.controllers.mca.handel.interface.get_module_type") as m3:
            m2.return_value = ((0,),)
            m3.return_value = "notfalconx"
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
    """ Test listing of config (.ini) files.
    warning: Adding files in this directory can break the test.
    """
    assert interface.get_config_files("tests/mca/mercury_config_file") == [
        "mercury.ini"
    ]
    assert interface.get_config_files(b"tests/mca/mercury_config_file") == [
        b"mercury.ini"
    ]


def test_get_config(interface):
    """ Test reading of configuration (.ini) files.
    warning: Adding files in this directory can break the test.
    """
    # Using string paths
    filename = interface.get_config_files("tests/mca/mercury_config_file")[0]
    conf = interface.get_config("tests/mca/mercury_config_file", filename)
    assert conf["detector definitions"][0]["alias"] == "detector1"
    with pytest.raises(IOError):
        interface.get_config("tests/mca/mercury_config_file", "i_dont_exist.ini")

    # Using bytestring paths
    filename = interface.get_config_files(b"tests/mca/mercury_config_file")[0]
    conf = interface.get_config(b"tests/mca/mercury_config_file", filename)
    assert conf["detector definitions"][0]["alias"] == "detector1"
    with pytest.raises(IOError):
        interface.get_config(b"tests/mca/mercury_config_file", b"i_dont_exist.ini")
