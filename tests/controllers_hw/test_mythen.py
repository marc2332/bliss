"""Hardware testing module for the Mythen."""

import socket

import pytest

from bliss.controllers.mca.mythen.lib import MythenInterface, Polarity
from bliss.controllers.mca.mythen.lib import (
    MythenCompatibilityError,
    MythenCommandError,
)


@pytest.fixture
def mythen(request, beacon):
    hostname = request.config.getoption("--mythen")
    if hostname is None:
        pytest.xfail("The --mythen hostname option has to be provided.")
    mythen = MythenInterface(hostname)
    yield mythen
    mythen.close()


def test_errors(mythen):
    with pytest.raises(MythenCompatibilityError) as info:
        mythen.get_commandsetid()
    assert (
        str(info.value)
        == "[Version 3.0.0] Command '-get commandsetid' requires version >= 4.0.0"
    )
    with pytest.raises(MythenCommandError) as info:
        mythen._run_command("-idontexist", "int")
    assert str(info.value) == "[Error -1] Unknown command ('-idontexist')"


def test_common_getters(mythen):
    assert mythen.get_version() == (3, 0, 0)
    assert mythen.get_nmodules() == 1
    assert mythen.get_modchannels() == (1280,)


def test_general_getters(mythen):

    assert mythen.get_assemblydate() == "Mon Aug 21 13:06:10 CEST 2017"
    assert all(x in (0, 1) for x in mythen.get_badchannels())
    assert mythen.get_commandid() + 1 == mythen.get_commandid()

    with pytest.raises(MythenCompatibilityError):
        mythen.get_commandsetid()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_dcstemperature()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_frameratemax()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_fwversion()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_humidity()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_highvoltage()
    with pytest.raises(MythenCompatibilityError):
        mythen.get_modfwversion()

    assert mythen.get_modnum() == ("0x192",)
    assert mythen.get_module() == 0xffff
    assert mythen.get_nmaxmodules() == 1
    assert mythen.get_sensormaterial() == ("silicon",)
    assert mythen.get_sensorthickness() == (1000,)

    with pytest.raises(MythenCompatibilityError):
        mythen.get_sensorwidth()

    assert mythen.get_systemnum() == 256

    with pytest.raises(MythenCompatibilityError):
        mythen.get_temperature()

    with pytest.raises(MythenCompatibilityError):
        mythen.get_testversion()


def test_general_commands(mythen):
    mythen.select_module(0)
    assert mythen.get_module() == 0
    mythen.select_all_modules()
    assert mythen.get_module() == 0xffff
    mythen.set_nmodules(1)
    assert mythen.get_nmodules() == 1
    mythen.reset()


def test_acquisition_settings(mythen):
    mythen.set_delayafterframe(1.)
    assert mythen.get_delayafterframe() == 1.
    mythen.set_delayafterframe()
    assert mythen.get_delayafterframe() == 0

    mythen.set_nframes(2)
    assert mythen.get_nframes() == 2
    mythen.set_nframes()
    assert mythen.get_nframes() == 1

    mythen.set_nbits(4)
    assert mythen.get_nbits() == 4
    mythen.set_nbits()
    assert mythen.get_nbits() == 24

    mythen.set_exposure_time(2.)
    assert mythen.get_exposure_time() == 2.
    mythen.set_exposure_time()
    assert mythen.get_exposure_time() == 1.

    status = mythen.get_status()
    assert not status.running
    assert not status.inactive_exposure
    assert status.empty_buffer

    with pytest.raises(MythenCompatibilityError):
        mythen.get_readouttimes()


def test_acquisition_control(mythen):
    # Configuration
    mythen.set_delayafterframe(0.05)
    mythen.set_exposure_time(0.05)
    mythen.set_nframes(5)

    # Start acquisition
    mythen.start()

    # Check status
    status = mythen.get_status()
    assert status.running
    assert not status.inactive_exposure
    assert status.empty_buffer

    # Wait for first frame
    array = mythen.readout()
    assert array.shape == (1, 1280)

    # Check status
    status = mythen.get_status()
    assert status.running
    assert not status.inactive_exposure
    assert status.empty_buffer

    # Wait for the last 4 frames
    with pytest.raises(MythenCompatibilityError):
        mythen.readout(4)
    for _ in range(4):
        array = mythen.readout(1)
        assert array.shape == (1, 1280)

    # Check status
    status = mythen.get_status()
    assert not status.running
    assert not status.inactive_exposure
    assert status.empty_buffer

    # Stop acquisition
    mythen.stop()

    # Check status
    status = mythen.get_status()
    assert not status.running
    assert not status.inactive_exposure
    assert status.empty_buffer


def test_detector_settings(mythen):
    mythen.set_energy(9.)
    assert mythen.get_energy() == (pytest.approx(9.),)
    mythen.set_energy()
    assert mythen.get_energy() == (pytest.approx(8.05),)

    assert mythen.get_energymin() == (pytest.approx(7.39),)
    assert mythen.get_energymax() == (pytest.approx(24.),)

    mythen.set_kthresh(7.)
    assert mythen.get_kthresh() == (pytest.approx(7.),)
    mythen.set_kthresh()
    assert mythen.get_kthresh() == (pytest.approx(6.4),)

    assert mythen.get_kthreshmin() == (pytest.approx(6.),)
    assert mythen.get_kthreshmax() == (pytest.approx(12.),)

    mythen.set_kthresh_and_energy(7., 9.)
    assert mythen.get_kthresh() == (pytest.approx(7.),)
    assert mythen.get_energy() == (pytest.approx(9.),)
    mythen.set_kthresh_and_energy()
    assert mythen.get_kthresh() == (pytest.approx(6.4),)
    assert mythen.get_energy() == (pytest.approx(8.05),)


def test_load_predefined_settings(mythen):
    with pytest.raises(ValueError):
        mythen.load_predefined_settings("Ar")
    for element in ("Cu", "Mo", "Ag"):
        mythen.load_predefined_settings(element)
    for element in ("Cr",):
        with pytest.raises(MythenCommandError):
            mythen.load_predefined_settings(element)


def test_data_correction(mythen):
    mythen.enable_badchannelinterpolation(True)
    assert mythen.badchannelinterpolation_enabled()
    mythen.enable_badchannelinterpolation(False)
    assert not mythen.badchannelinterpolation_enabled()

    mythen.enable_flatfieldcorrection(True)
    assert mythen.flatfieldcorrection_enabled()
    mythen.enable_flatfieldcorrection(False)
    assert not mythen.flatfieldcorrection_enabled()

    with pytest.raises(MythenCompatibilityError):
        mythen.set_flatfield(0, [1, 2, 3])
    with pytest.raises(MythenCompatibilityError):
        mythen.load_flatfield(1)
    assert mythen.get_flatfield().shape == (1280,)
    assert mythen.get_flatfield_cutoff() == 16777216

    mythen.enable_ratecorrection(True)
    assert mythen.ratecorrection_enabled()
    mythen.enable_ratecorrection(False)
    assert not mythen.ratecorrection_enabled()

    mythen.set_ratecorrection_deadtime(400 * 1e-9)
    assert mythen.get_ratecorrection_deadtime() == pytest.approx(400 * 1e-9)
    mythen.set_ratecorrection_deadtime(-1)
    default = 140.400573 * 1e-9
    assert mythen.get_ratecorrection_deadtime() == pytest.approx(default)


def test_trigger_and_gate(mythen):
    mythen.enable_continuoustrigger(True)
    assert mythen.continuoustrigger_enabled()
    mythen.enable_continuoustrigger(False)
    assert not mythen.continuoustrigger_enabled()

    mythen.enable_singletrigger(True)
    assert mythen.singletrigger_enabled()
    mythen.enable_singletrigger(False)
    assert not mythen.singletrigger_enabled()

    mythen.set_delaybeforeframe(.5)
    assert mythen.get_delaybeforeframe() == pytest.approx(.5)
    mythen.set_delaybeforeframe()
    assert mythen.get_delaybeforeframe() == pytest.approx(0.)

    mythen.enable_gatemode(True)
    assert mythen.gatemode_enabled()
    mythen.enable_gatemode(False)
    assert not mythen.gatemode_enabled()

    mythen.set_ngates(10)
    assert mythen.get_ngates() == 10
    mythen.set_ngates()
    assert mythen.get_ngates() == 1

    mythen.set_inputpolarity(Polarity.High)
    assert mythen.get_inputpolarity() == Polarity.High
    mythen.set_inputpolarity(Polarity.Low)
    assert mythen.get_inputpolarity() == Polarity.Low

    mythen.set_outputpolarity(Polarity.High)
    assert mythen.get_outputpolarity() == Polarity.High
    mythen.set_outputpolarity(Polarity.Low)
    assert mythen.get_outputpolarity() == Polarity.Low


def test_debugging(mythen):
    mythen.start_logging()
    with pytest.raises(MythenCompatibilityError):
        assert mythen.logging_running()
    logs = mythen.stop_logging()
    assert "Command: -log argument: stop" in logs

    data = mythen.test_pattern()
    assert data.shape == (1280,)
    assert list(data) == list(range(1280))


@pytest.mark.parametrize("nbits", [4, 8, 16, 24])
def test_raw_readout(mythen, nbits):
    # Configuration
    mythen.set_nbits(nbits)
    mythen.set_delayafterframe(0.05)
    mythen.set_exposure_time(0.05)
    mythen.set_nframes(1)

    # Start acquisition
    mythen.start()

    # Wait for the frame
    array = mythen.raw_readout()
    assert array.shape == (1280,)

    # Stop acquisition
    mythen.stop()
