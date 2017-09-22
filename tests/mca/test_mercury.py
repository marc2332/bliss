"""Test module for the Mercury MCA."""

import pytest

from bliss.controllers.mca import Brand, DetectorType, Stats
from bliss.controllers.mca import PresetMode, TriggerMode


@pytest.fixture
def mercury(beacon, mocker):
    beacon.reload()
    m = mocker.patch('zerorpc.Client')
    client = m.return_value
    client.get_detectors.return_value = ['detector1']
    client.get_modules.return_value = ['module1']
    client.get_channels.return_value = (0,)
    client.get_grouped_channels.return_value = ((0, ), )
    client.get_config_files.return_value = ['default.ini']
    client.get_config.return_value = {'my': 'config'}
    client.is_running.return_value = True

    # Emulate running behavior
    def mock_not_running():
        client.is_running.return_value = False
    client.mock_not_running = mock_not_running

    # Instantiating the mercury
    mercury = beacon.get('mercury1')
    assert mercury._proxy is client
    m.assert_called_once_with('tcp://welisa.esrf.fr:8000')
    yield mercury


def test_mercury_instanciation(mercury):
    client = mercury._proxy
    client.init.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')
    assert mercury.current_configuration == 'mercury_src.ini'
    assert mercury.configured


def test_mercury_infos(mercury):
    assert mercury.detector_brand == Brand.XIA
    assert mercury.detector_type == DetectorType.MERCURY
    assert mercury.element_count == 1


def test_mercury_configuration(mercury):
    client = mercury._proxy
    assert mercury.available_configurations == ['default.ini']
    client.get_config_files.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury')
    assert mercury.current_configuration_values == {'my': 'config'}
    client.get_config.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')


def test_mercury_preset_mode(mercury):
    client = mercury._proxy

    # First test
    mercury.set_preset_mode(None)
    assert client.set_acquisition_value.call_args_list == \
        [(('preset_type', 0),), (('preset_value', 0),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Error tests
    with pytest.raises(ValueError):
        mercury.set_preset_mode(3)
    with pytest.raises(TypeError):
        mercury.set_preset_mode(PresetMode.NONE, 1)
    with pytest.raises(TypeError):
        mercury.set_preset_mode(PresetMode.REALTIME, None)


def test_mercury_trigger_mode(mercury):
    client = mercury._proxy

    # First test
    mercury.set_trigger_mode(None)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 1),),
        (('pixel_advance_mode', 0),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Second test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    mercury.set_trigger_mode(TriggerMode.GATE)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 0),),
        (('pixel_advance_mode', 1),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Third test
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    client.get_acquisition_value.return_value = 2  # Multiple
    mercury.set_trigger_mode(TriggerMode.EXTERNAL)
    assert client.set_acquisition_value.call_args_list == [
        (('gate_ignore', 1),),
        (('pixel_advance_mode', 1),)]
    client.apply_acquisition_values.assert_called_once_with()

    # First error tests
    client.get_acquisition_value.return_value = 0  # Single
    with pytest.raises(ValueError):
        mercury.set_trigger_mode(TriggerMode.EXTERNAL)

    # Second error tests
    with pytest.raises(ValueError):
        mercury.set_trigger_mode(13)


def test_mercury_acquisition_number(mercury):
    client = mercury._proxy

    # Test single setter
    mercury.set_acquisition_number(1)
    client.set_acquisition_value.assert_called_once_with('mapping_mode', 0)
    client.apply_acquisition_values.assert_called_once_with()

    # Test single getter
    client.get_acquisition_value.return_value = 0.
    assert mercury.acquisition_number == 1
    client.get_acquisition_value.assert_called_once_with('mapping_mode', 0)

    # Test multi setter
    client.set_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    mercury.set_acquisition_number(2)
    assert client.set_acquisition_value.call_args_list == [
        (('mapping_mode', 1),), (('num_map_pixels', 2),)]
    client.apply_acquisition_values.assert_called_once_with()

    # Test multi getter
    values = [1, 2]
    client.get_acquisition_value.reset_mock()
    client.get_acquisition_value.side_effect = lambda *args: values.pop(0)
    assert mercury.acquisition_number == 2
    assert client.get_acquisition_value.call_args_list == [
        (('mapping_mode', 0),), (('num_map_pixels', 0),)]

    # Error tests
    with pytest.raises(ValueError):
        mercury.set_acquisition_number(0)


def test_mercury_block_size(mercury):
    client = mercury._proxy

    # Test simple setter
    assert mercury.set_block_size(3) is None
    client.set_acquisition_value.assert_called_once_with(
        'num_map_pixels_per_buffer', 3)
    client.apply_acquisition_values.assert_called_once_with()

    # Test simple getter
    client.get_acquisition_value.return_value = 3
    mercury.block_size == 3
    client.get_acquisition_value.assert_called_once_with(
        'num_map_pixels_per_buffer', 0)

    # Test default setter
    client.set_acquisition_value.reset_mock()
    client.get_acquisition_value.reset_mock()
    client.apply_acquisition_values.reset_mock()
    client.get_acquisition_value.return_value = 10.
    assert mercury.set_block_size() is None
    assert client.set_acquisition_value.call_args_list == [
        (('num_map_pixels_per_buffer', -1),),
        (('num_map_pixels_per_buffer', 10),)]
    client.get_acquisition_value.assert_called_once_with(
        'num_map_pixels_per_buffer', 0)


def test_mercury_acquisition(mercury, mocker):
    client = mercury._proxy
    sleep = mocker.patch('time.sleep')
    sleep.side_effect = lambda x: client.mock_not_running()
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(7)}
    stats = Stats(*range(7))
    assert mercury.run_single_acquisition(3.) == ([[3, 2, 1]], [stats])
    sleep.assert_called_once_with(0.1)


def test_mercury_multiple_acquisition(mercury, mocker):
    client = mercury._proxy
    sleep = mocker.patch('time.sleep')
    sleep.side_effect = lambda x: client.mock_not_running()
    client.get_acquisition_value.return_value = 2
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(9)}
    client.synchronized_poll_data.side_effect = lambda: data.pop(0)

    data = [(0, {}, {}),
            (1, {0: {0: 'spectrum0'}}, {0: {0: range(7)}}),
            (2, {1: {0: 'spectrum1'}}, {1: {0: range(10, 17)}})]
    stats0, stats1 = Stats(*range(7)), Stats(*range(10, 17))

    data, stats = mercury.run_multiple_acquisitions(3)
    assert data == {0: ['spectrum0'], 1: ['spectrum1']}
    assert stats == {0: [stats0], 1: [stats1]}
    assert sleep.call_args_list == [((0.1,),), ((0.1,),)]


def test_mercury_configuration_error(mercury):
    client = mercury._proxy
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        mercury.load_configuration('i-dont-exist')
    assert not mercury.configured
    assert mercury.current_configuration is None
    assert mercury.current_configuration_values is None


def test_mercury_finalization(mercury):
    client = mercury._proxy
    mercury.finalize()
    client.close.assert_called_once_with()


def test_mercury_from_wrong_beacon_config(beacon, mocker):
    # ZeroRPC error
    beacon.reload()
    m = mocker.patch('zerorpc.Client')
    m.side_effect = IOError('Cannot connect!')
    with pytest.raises(IOError):
        beacon.get('mercury1')

    # Handel error
    m = mocker.patch('zerorpc.Client')
    client = m.return_value
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        beacon.get('mercury1')
