"""Test module for MCA base class."""

import pytest
from bliss.controllers.mca import BaseMCA, Brand, DetectorType


def test_mca_enums():
    assert 'XIA' in dir(Brand)
    assert 'MERCURY' in dir(DetectorType)


def test_base_mca():

    class IncompleteMCA(BaseMCA):
        pass

    # Create an incomplete mca
    config = {}
    mca = IncompleteMCA('incomplete', config)
    assert mca.name == 'incomplete'
    assert mca.config is config

    # Method dict
    methods = {
        mca.get_detector_brand: (),
        mca.get_detector_type: (),
        mca.get_element_count: (),
        mca.get_supported_preset_modes: (),
        mca.set_preset_mode: ('some_mode',),
        mca.get_supported_acquisition_modes: (),
        mca.set_acquisition_mode: ('some_mode',),
        mca.get_supported_trigger_mode: (),
        mca.set_trigger_mode: ('some_mode',),
        mca.has_calibration: (),
        mca.get_calibration_type: (),
        mca.set_spectrum_range: ('some', 'range'),
        mca.prepare_acquisition: (),
        mca.start_acquisition: (),
        mca.stop_acquisition: (),
        mca.get_acquisition_status: (),
        mca.get_acquisition_data: ()}

    # Test methods
    for method, args in methods.items():
        with pytest.raises(NotImplementedError):
            method(*args)


def test_base_mca_logic(mocker):

    class TestMCA(BaseMCA):

        def prepare_acquisition(self):
            pass

        def start_acquisition(self):
            pass

        def stop_acquisition(self):
            pass

        def get_acquisition_status(self):
            return ""

        def get_acquisition_data(self):
            return [[3, 2, 1]]

    # Create a test mca
    config = {}
    mca = TestMCA('incomplete', config)
    assert mca.name == 'incomplete'
    assert mca.config is config

    # Run a single acquisition
    sleep = mocker.patch('time.sleep')
    assert mca.run_single_acquisition(3.) == [[3, 2, 1]]
    sleep.assert_called_once_with(3.)
