"""Test module for MCA base class."""

import pytest
from bliss.controllers.mca import (
    BaseMCA,
    Brand,
    DetectorType,
    PresetMode,
    TriggerMode,
    Stats,
)
from bliss.controllers.mca import PresetMode, TriggerMode, Stats


def test_mca_enums():
    assert "XIA" in dir(Brand)
    assert "MERCURY" in dir(DetectorType)


def test_base_mca(beacon):

    # No initialize_attributes method
    class IncompleteMCA1(BaseMCA):
        pass

    with pytest.raises(NotImplementedError):
        IncompleteMCA1("incomplete", {})

    # No initialize_hardware method
    class IncompleteMCA2(BaseMCA):
        def initialize_attributes(self):
            pass

    with pytest.raises(NotImplementedError):
        IncompleteMCA2("incomplete", {})

    # Missing methods and properties
    class IncompleteMCA3(BaseMCA):
        def initialize_attributes(self):
            pass

        def initialize_hardware(self):
            pass

    # Create an incomplete mca
    config = {}
    mca = IncompleteMCA3("incomplete", config)
    assert mca.name == "incomplete"
    assert mca.config is config

    # Method dict
    methods = {
        mca.finalize: (),
        mca.start_acquisition: (),
        mca.stop_acquisition: (),
        mca.is_acquiring: (),
        mca.get_acquisition_data: (),
        mca.get_acquisition_statistics: (),
        mca.poll_data: (),
    }

    # Test methods
    for method, args in list(methods.items()):
        with pytest.raises(NotImplementedError):
            method(*args)

    # Property list
    properties = [
        "detector_brand",
        "detector_type",
        "elements",
        "preset_mode",
        "preset_value",
        "spectrum_range",
        "spectrum_size",
        "trigger_mode",
        "hardware_points",
        "block_size",
        "supported_preset_modes",
        "supported_trigger_modes",
        "calibration_type",
    ]

    # Test properties
    for prop in properties:
        with pytest.raises(NotImplementedError):
            getattr(mca, prop)


def test_base_mca_logic(beacon):
    stats = Stats(*list(range(1, 8)))

    class TestMCA(BaseMCA):

        supported_preset_modes = [PresetMode.NONE, PresetMode.REALTIME]

        @property
        def preset_mode(self):
            return PresetMode.NONE

        @preset_mode.setter
        def preset_mode(self, mode):
            assert mode is None or mode in self.supported_preset_modes

        @property
        def preset_value(self):
            return 3.0

        @preset_value.setter
        def preset_value(self, value):
            assert value == 3.0

        supported_trigger_modes = [TriggerMode.SOFTWARE, TriggerMode.GATE]

        @property
        def trigger_mode(self):
            return TriggerMode.SOFTWARE

        @trigger_mode.setter
        def trigger_mode(self, mode):
            assert mode is None or mode in self.supported_trigger_modes

        @property
        def hardware_points(self):
            return 1

        @hardware_points.setter
        def hardware_points(self, value):
            assert value == 1

        def initialize_attributes(self):
            pass

        def initialize_hardware(self):
            pass

        def start_acquisition(self):
            pass

        def stop_acquisition(self):
            pass

        def is_acquiring(self):
            return False

        def get_acquisition_data(self):
            return {0: [3, 2, 1]}

        def get_acquisition_statistics(self):
            return {0: stats}

    # Create a test mca
    config = {}
    mca = TestMCA("incomplete", config)
    assert mca.name == "incomplete"
    assert mca.config is config

    # Run a single acquisition
    assert mca.run_software_acquisition(1, 3.) == ([{0: [3, 2, 1]}], [{0: stats}])
