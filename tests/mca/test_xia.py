"""Test module for the XIA MCAs."""

import pytest

from bliss.controllers.mca import Brand, DetectorType, Stats
from bliss.controllers.mca import PresetMode, TriggerMode
from bliss.controllers.mca import XIA, XMAP


@pytest.fixture(params=["xia", "mercury", "xmap", "falconx"])
def xia(request, beacon, mocker):
    # Mocking
    m = mocker.patch("bliss.controllers.mca.xia.zerorpc.Client")
    client = m.return_value

    # Modules
    client.get_detectors.return_value = ["detector1"]
    client.get_modules.return_value = ["module1"]

    # Elements
    client.get_channels.return_value = (0, 1, 2, 3)

    # Configuration
    client.get_config_files.return_value = ["some_config.ini"]
    client.get_config.return_value = {"my": "config"}
    mtype = "mercury" if request.param == "xia" else request.param
    client.get_module_type.return_value = mtype

    # Emulate running behavior
    client.is_running.return_value = True

    def mock_not_running():
        client.is_running.return_value = False

    client.mock_not_running = mock_not_running

    # Instantiating the xia
    xia = beacon.get(request.param + "1")
    assert xia._proxy is client
    m.assert_called_once_with(xia._config["url"])
    yield xia


def test_xia_instanciation(xia):
    client = xia._proxy
    config_dir = xia._config["configuration_directory"]
    default = xia._config["default_configuration"]
    client.init.assert_called_once_with(config_dir, default)
    assert xia.current_configuration == default
    assert xia.configured


def test_xia_infos(xia):
    assert xia.detector_brand == Brand.XIA
    if type(xia) is XIA:
        assert xia.detector_type == DetectorType.MERCURY
    else:
        name = type(xia).__name__.upper()
        assert xia.detector_type == getattr(DetectorType, name)
    assert xia.elements == (0, 1, 2, 3)


def test_xia_configuration(xia):
    client = xia._proxy
    config_dir = xia._config["configuration_directory"]
    default = xia._config["default_configuration"]
    assert xia.available_configurations == ["some_config.ini"]
    client.get_config_files.assert_called_once_with(config_dir)
    assert xia.current_configuration_values == {"my": "config"}
    client.get_config.assert_called_once_with(config_dir, default)


def test_xia_preset_mode(xia):
    client = xia._proxy

    # First test
    xia.set_preset_mode(None)
    assert client.set_acquisition_value.call_args_list == [
        (("preset_type", 0),),
        (("preset_value", 0),),
    ]
    client.apply_acquisition_values.assert_called_once_with()

    # Error tests
    with pytest.raises(ValueError):
        xia.set_preset_mode(3)
    with pytest.raises(TypeError):
        xia.set_preset_mode(PresetMode.NONE, 1)
    with pytest.raises(TypeError):
        xia.set_preset_mode(PresetMode.REALTIME, None)


def test_xia_trigger_mode(xia):
    client = xia._proxy

    # XMAP specific tests
    xmap = isinstance(xia, XMAP)
    if xmap:
        client.get_trigger_channels.return_value = [0]
        xmap_prefix = [(("gate_master", True, 0),)]
    else:
        xmap_prefix = []

    # First test
    xia.set_trigger_mode(None)
    assert client.set_acquisition_value.call_args_list == [
        (("gate_ignore", 1),),
        (("mapping_mode", 0),),
    ]
    client.apply_acquisition_values.assert_called_once_with()

    # Second test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    xia.set_trigger_mode(TriggerMode.GATE)
    assert client.set_acquisition_value.call_args_list == xmap_prefix + [
        (("gate_ignore", 0),),
        (("mapping_mode", 1),),
        (("pixel_advance_mode", 1),),
    ]
    client.apply_acquisition_values.assert_called_once_with()

    # Third test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    client.get_acquisition_value.return_value = 3  # Multiple
    xia.set_trigger_mode(TriggerMode.SYNC)
    assert client.set_acquisition_value.call_args_list == xmap_prefix + [
        (("gate_ignore", 1),),
        (("mapping_mode", 1),),
        (("pixel_advance_mode", 1),),
    ]
    client.apply_acquisition_values.assert_called_once_with()

    # Error tests
    with pytest.raises(ValueError):
        xia.set_trigger_mode(13)

    # XMAP specific
    if xmap:
        client.get_trigger_channels.return_value = []
        with pytest.raises(ValueError):
            xia.set_trigger_mode(TriggerMode.GATE)

    # XMAP specific
    if xmap:
        client.get_trigger_channels.return_value = [0]
        with pytest.raises(ValueError):
            xia.set_trigger_mode(TriggerMode.GATE, channel=1)


def test_xia_hardware_points(xia):
    client = xia._proxy

    # Test single setter
    client.get_acquisition_value.return_value = 1.
    xia.set_hardware_points(3)
    client.set_acquisition_value.assert_called_once_with("num_map_pixels", 3)
    client.apply_acquisition_values.assert_called_once_with()

    # Test single getter
    values = [1., 3.]
    client.get_acquisition_value.reset_mock()
    client.get_acquisition_value.side_effect = lambda *args: values.pop(0)
    assert xia.hardware_points == 3
    assert client.get_acquisition_value.call_args_list == [
        (("mapping_mode",),),
        (("num_map_pixels",),),
    ]

    # Error tests
    with pytest.raises(ValueError):
        xia.set_hardware_points(0)


def test_xia_block_size(xia):
    client = xia._proxy

    # Test simple setter
    assert xia.set_block_size(3) is None
    client.set_acquisition_value.assert_called_once_with("num_map_pixels_per_buffer", 3)
    client.apply_acquisition_values.assert_called_once_with()

    # Test simple getter
    client.get_acquisition_value.reset_mock()
    client.get_acquisition_value.return_value = 3
    xia.block_size == 3
    assert client.get_acquisition_value.call_args_list == [
        (("mapping_mode",),),
        (("num_map_pixels_per_buffer",),),
    ]

    # Test default setter
    client.apply_acquisition_values.reset_mock()
    assert xia.set_block_size() is None
    client.set_maximum_pixels_per_buffer.assert_called_once_with()
    client.apply_acquisition_values.assert_called_once_with()


def test_xia_software_acquisition(xia, mocker):
    client = xia._proxy
    sleep = mocker.patch("gevent.sleep")
    sleep.side_effect = lambda x: client.mock_not_running()
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(7)}
    stats = Stats(*range(7))
    assert xia.run_software_acquisition(1, 3.) == ([{0: [3, 2, 1]}], [{0: stats}])


def test_xia_multiple_acquisition(xia, mocker):
    client = xia._proxy
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(9)}
    client.synchronized_poll_data.side_effect = lambda: data.pop(0)

    data = [
        (1, {0: {0: "discarded"}}, {0: {0: [0] * 7}}),
        (2, {1: {0: "spectrum0"}}, {1: {0: range(7)}}),
        (3, {2: {0: "spectrum1"}}, {2: {0: range(10, 17)}}),
    ]
    stats0, stats1 = Stats(*range(7)), Stats(*range(10, 17))

    data, stats = xia.run_synchronized_acquisition(2)
    assert data == [{0: "spectrum0"}, {0: "spectrum1"}]
    assert stats == [{0: stats0}, {0: stats1}]


def test_xia_configuration_error(xia):
    client = xia._proxy
    client.init.side_effect = IOError("File not found!")
    with pytest.raises(IOError):
        xia.load_configuration("i-dont-exist")
    assert not xia.configured
    assert xia.current_configuration is None
    assert xia.current_configuration_values is None


def test_xia_finalization(xia):
    client = xia._proxy
    xia.finalize()
    client.close.assert_called_once_with()


@pytest.mark.parametrize("dtype", ["xia", "mercury", "xmap", "falconx"])
def test_xia_from_wrong_beacon_config(dtype, beacon, mocker):
    # ZeroRPC error
    m = mocker.patch("bliss.controllers.mca.xia.zerorpc.Client")
    m.side_effect = IOError("Cannot connect!")
    with pytest.raises(IOError):
        beacon.get(dtype + "1")

    # Handel error
    m = mocker.patch("bliss.controllers.mca.xia.zerorpc.Client")
    client = m.return_value
    client.init.side_effect = IOError("File not found!")
    with pytest.raises(IOError):
        beacon.get(dtype + "1")
