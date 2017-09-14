"""Test module for the Mercury MCA."""

import pytest

from bliss.controllers.mca import Brand, DetectorType, Stats


def test_get_mercury_from_config(beacon, mocker):
    # Mocking
    beacon.reload()
    m = mocker.patch('zerorpc.Client')
    client = m.return_value
    client.get_detectors.return_value = ['detector1']
    client.get_modules.return_value = ['module1']
    client.get_channels.return_value = (0,)
    client.get_grouped_channels.return_value = ((0, ), )
    client.get_config_files.return_value = ['default.ini']
    client.get_config.return_value = {'my': 'config'}
    client.is_running.return_value = False

    # Instantiating the mercury
    mercury = beacon.get('mercury-test')
    m.assert_called_once_with('tcp://welisa.esrf.fr:8000')
    client.init.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')
    assert mercury.configured

    # Infos
    assert mercury.detector_brand == Brand.XIA
    assert mercury.detector_type == DetectorType.MERCURY
    assert mercury.element_count == 1

    # Configuration
    assert mercury.available_configurations == ['default.ini']
    client.get_config_files.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury')
    assert mercury.current_configuration_values == {'my': 'config'}
    client.get_config.assert_called_once_with(
        'C:\\\\blissadm\\\\mercury', 'mercury_src.ini')

    # Acquisition
    client.get_spectrums.return_value = {0: [3, 2, 1]}
    client.get_statistics.return_value = {0: range(7)}
    stats = Stats(*range(7))
    assert mercury.run_single_acquisition(3.) == ([[3, 2, 1]], [stats])

    # Load configuration
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        mercury.load_configuration('i-dont-exist')
    assert not mercury.configured


def test_get_mercury_from_wrong_config(beacon, mocker):
    # ZeroRPC error
    beacon.reload()
    m = mocker.patch('zerorpc.Client')
    m.side_effect = IOError('Cannot connect!')
    with pytest.raises(IOError):
        beacon.get('mercury-test')

    # Handel error
    m = mocker.patch('zerorpc.Client')
    client = m.return_value
    client.init.side_effect = IOError('File not found!')
    with pytest.raises(IOError):
        beacon.get('mercury-test')
