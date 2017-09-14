"""Test module for MCA base class."""

import pytest
from bliss.controllers.mca import BaseMCA, Brand, DetectorType, PresetMode


def test_mca_enums():
    assert 'XIA' in dir(Brand)
    assert 'MERCURY' in dir(DetectorType)


def test_base_mca():

    # No initialize_attributes method
    class IncompleteMCA1(BaseMCA):
        pass

    with pytest.raises(NotImplementedError):
        IncompleteMCA1('incomplete', {})

    # No initialize_hardware method
    class IncompleteMCA2(BaseMCA):

        def initialize_attributes(self):
            pass

    with pytest.raises(NotImplementedError):
        IncompleteMCA2('incomplete', {})

    # Missing methods and properties
    class IncompleteMCA3(BaseMCA):

        def initialize_attributes(self):
            pass

        def initialize_hardware(self):
            pass

    # Create an incomplete mca
    config = {}
    mca = IncompleteMCA3('incomplete', config)
    assert mca.name == 'incomplete'
    assert mca._config is config

    # Method dict
    methods = {
        mca.finalize: (),
        mca.set_preset_mode: ('some_mode',),
        mca.set_acquisition_mode: ('some_mode',),
        mca.set_trigger_mode: ('some_mode',),
        mca.set_spectrum_range: ('some', 'range'),
        mca.prepare_acquisition: (),
        mca.start_acquisition: (),
        mca.stop_acquisition: (),
        mca.is_acquiring: (),
        mca.get_acquisition_data: (),
        mca.get_acquisition_statistics: ()}

    # Test methods
    for method, args in methods.items():
        with pytest.raises(NotImplementedError):
            method(*args)

    # Property list
    properties = [
        'detector_brand',
        'detector_type',
        'element_count',
        'supported_preset_modes',
        'supported_acquisition_modes',
        'supported_trigger_modes',
        'calibration_type']

    # Test properties
    for prop in properties:
        with pytest.raises(NotImplementedError):
            getattr(mca, prop)


def test_base_mca_logic(mocker):

    class TestMCA(BaseMCA):

        supported_preset_modes = [PresetMode.NONE]

        def set_preset_mode(self, mode):
            assert mode in (None, PresetMode.NONE)

        def initialize_attributes(self):
            pass

        def initialize_hardware(self):
            pass

        def prepare_acquisition(self):
            pass

        def start_acquisition(self):
            pass

        def stop_acquisition(self):
            pass

        def is_running(self):
            return False

        def get_acquisition_data(self):
            return [[3, 2, 1]]

        def get_acquisition_statistics(self):
            return ['some_stats']

    # Create a test mca
    config = {}
    mca = TestMCA('incomplete', config)
    assert mca.name == 'incomplete'
    assert mca._config is config

    # Run a single acquisition
    sleep = mocker.patch('time.sleep')
    assert mca.run_single_acquisition(3.) == ([[3, 2, 1]], ['some_stats'])
    sleep.assert_called_once_with(3.)
