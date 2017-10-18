"""Test module for the XIA MCAs."""

import pytest

from bliss.controllers.mca import Brand, DetectorType, Stats
from bliss.controllers.mca import PresetMode, TriggerMode
from bliss.controllers.xia import XIA, Mercury


@pytest.fixture(
    params=['xia', 'mercury', 'mercury4', 'xmap',
            'falconx', 'falconx4', 'falconx8'])
def xia(request, beacon, mocker):
    beacon.reload()

    # Mocking
    m = mocker.patch('zerorpc.Client')
    client = m.return_value

    # Modules
    client.get_detectors.return_value = ['detector1']
    client.get_modules.return_value = ['module1']

    # Element count
    channels = (0,) if request.param == 'mercury' else (0, 1, 2, 3)
    client.get_channels.return_value = channels

    # Configuration
    client.get_config_files.return_value = ['default.ini']
    client.get_config.return_value = {'my': 'config'}
    mtype = 'mercury4' if request.param == 'xia' else request.param
    client.get_module_type.return_value = mtype

    # Emulate running behavior
    client.is_running.return_value = True

    def mock_not_running():
        client.is_running.return_value = False
    client.mock_not_running = mock_not_running

    # Instantiating the xia
    xia = beacon.get(request.param + '1')
    assert xia._proxy is client
    m.assert_called_once_with('tcp://welisa.esrf.fr:8000')
    yield xia


def test_xia_instanciation(xia):
    client = xia._proxy
    client.init.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')
    assert xia.current_configuration == 'mercury_src.ini'
    assert xia.configured


def test_xia_infos(xia):
    assert xia.detector_brand == Brand.XIA
    if type(xia) is XIA:
        assert xia.detector_type == DetectorType.MERCURY4
    else:
        name = type(xia).__name__.upper()
        assert xia.detector_type == getattr(DetectorType, name)
    if type(xia) is Mercury:
        assert xia.element_count == 1
    else:
        assert xia.element_count == 4


def test_xia_configuration(xia):
    client = xia._proxy
    assert xia.available_configurations == ['default.ini']
    client.get_config_files.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury')
    assert xia.current_configuration_values == {'my': 'config'}
    client.get_config.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')


def test_xia_preset_mode(xia):
    client = xia._proxy

    # First test
    xia.set_preset_mode(None)
    assert client.set_acquisition_value.call_args_list == \
        [(('preset_type', 0),), (('preset_value', 0),)]
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

    # First test
    xia.set_trigger_mode(None)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 1),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Second test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    xia.set_trigger_mode(TriggerMode.GATE)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 0),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Third test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    client.get_acquisition_value.return_value = 3  # Multiple
    xia.set_trigger_mode(TriggerMode.EXTERNAL)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 1),),
        (('pixel_advance_mode', 1),)]
    client.apply_acquisition_values.assert_called_once_with()

    # First error tests
    client.get_acquisition_value.return_value = 0  # Single
    with pytest.raises(ValueError):
        xia.set_trigger_mode(TriggerMode.EXTERNAL)

    # Second error tests
    with pytest.raises(ValueError):
        xia.set_trigger_mode(13)


def test_xia_acquisition_number(xia):
    client = xia._proxy

    # Test single setter
    xia.set_acquisition_number(1)
    client.set_acquisition_value.assert_called_once_with('mapping_mode', 0)
    client.apply_acquisition_values.assert_called_once_with()

    # Test single getter
    client.get_acquisition_value.return_value = 0.
    assert xia.acquisition_number == 1
    client.get_acquisition_value.assert_called_once_with('mapping_mode')

    # Test multi setter
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    xia.set_acquisition_number(2)
    assert client.set_acquisition_value.call_args_list == [
        (('mapping_mode', 1),), (('num_map_pixels', 3),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Test multi getter
    values = [1, 3]
    client.get_acquisition_value.reset_mock()
    client.get_acquisition_value.side_effect = lambda *args: values.pop(0)
    assert xia.acquisition_number == 2
    assert client.get_acquisition_value.call_args_list == [
        (('mapping_mode',),), (('num_map_pixels',),)]

    # Error tests
    with pytest.raises(ValueError):
        xia.set_acquisition_number(0)


def test_xia_block_size(xia):
    client = xia._proxy

    # Test simple setter
    assert xia.set_block_size(3) is None
    client.set_acquisition_value.assert_called_once_with(
        'num_map_pixels_per_buffer', 3)
    client.apply_acquisition_values.assert_called_once_with()

    # Test simple getter
    client.get_acquisition_value.return_value = 3
    xia.block_size == 3
    client.get_acquisition_value.assert_called_once_with(
        'num_map_pixels_per_buffer')

    # Test default setter
    client.apply_acquisition_values.reset_mock()
    assert xia.set_block_size() is None
    client.set_maximum_pixels_per_buffer.assert_called_once_with()
    client.apply_acquisition_values.assert_called_once_with()


def test_xia_acquisition(xia, mocker):
    client = xia._proxy
    sleep = mocker.patch('time.sleep')
    sleep.side_effect = lambda x: client.mock_not_running()
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(7)}
    stats = Stats(*range(7))
    assert xia.run_single_acquisition(3.) == ([[3, 2, 1]], [stats])
    sleep.assert_called_once_with(0.1)


def test_xia_multiple_acquisition(xia, mocker):
    client = xia._proxy
    sleep = mocker.patch('time.sleep')
    sleep.side_effect = lambda x: client.mock_not_running()
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(9)}
    client.synchronized_poll_data.side_effect = lambda: data.pop(0)

    data = [(1, {0: 'discarded'}, {0: 'discarded'}),
            (2, {1: {0: 'spectrum0'}}, {1: {0: range(7)}}),
            (3, {2: {0: 'spectrum1'}}, {2: {0: range(10, 17)}})]
    stats0, stats1 = Stats(*range(7)), Stats(*range(10, 17))

    data, stats = xia.run_multiple_acquisitions(2)
    assert data == {0: ['spectrum0'], 1: ['spectrum1']}
    assert stats == {0: [stats0], 1: [stats1]}
    assert sleep.call_args_list == [((0.1,),), ((0.1,),)]


def test_xia_configuration_error(xia):
    client = xia._proxy
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        xia.load_configuration('i-dont-exist')
    assert not xia.configured
    assert xia.current_configuration is None
    assert xia.current_configuration_values is None


def test_xia_finalization(xia):
    client = xia._proxy
    xia.finalize()
    client.close.assert_called_once_with()


@pytest.mark.parametrize(
    'dtype',
    ['xia', 'mercury', 'mercury4', 'xmap', 'falconx', 'falconx4', 'falconx8'])
def test_xia_from_wrong_beacon_config(dtype, beacon, mocker):
    # ZeroRPC error
    beacon.reload()
    m = mocker.patch('zerorpc.Client')
    m.side_effect = IOError('Cannot connect!')
    with pytest.raises(IOError):
        beacon.get(dtype + '1')

    # Handel error
    m = mocker.patch('zerorpc.Client')
    client = m.return_value
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        beacon.get(dtype + '1')
