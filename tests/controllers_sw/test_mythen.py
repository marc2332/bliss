
import pytest
import numpy as np

from mock import Mock

from bliss.common import scans
from bliss.controllers.mca.mythen import Mythen
from bliss.controllers.mca.mythen import lib as mythenlib
from bliss.shell.standard import info


@pytest.fixture
def run_command(monkeypatch):
    setters = {}
    commands = []

    def run_command(sock, command, return_type="int", return_shape=(), payload=b""):
        # General commands
        if command == "-get version":
            return "v3.0.0"
        if command == "-get nmodules":
            return 1

        # Detect setters
        args = command[1:].split(" ")
        if args[0] == "readout":
            assert args[1:] == ["1"]
            args = args[:1]
        if len(args) == 2 and args[0] != "get":
            setters[args[0]] = args[1]
        if len(args) == 1:
            commands.append(args[0])

        # Return values
        if return_shape == ():
            return {
                "int": 0,
                "float": 1.23e9 if "tau" in command else 4.56,
                "long long": 31400000,
            }[return_type]
        if return_shape == (1,):
            return np.array([run_command(sock, command, return_type, (), payload)])
        if return_shape == (1, 1280):
            return np.array(range(1280)).reshape(return_shape)

        # Not managed
        assert False

    monkeypatch.setattr(mythenlib, "Socket", Mock())
    monkeypatch.setattr(mythenlib, "run_command", run_command)
    run_command.setters = setters
    run_command.commands = commands
    yield run_command


def test_mythen_basic(beacon, run_command):
    m = Mythen("test", {"hostname": "mymythen"})
    assert m.name == "test"
    assert m.hostname == "mymythen"
    assert (
        info(m)
        == """\
Mythen on mymythen:
  nmodules                  = 1
  delay_after_frame         = 3.14
  nframes                   = 0
  nbits                     = 0
  exposure_time             = 3.14
  energy                    = (4.56,)
  threshold                 = (4.56,)
  bad_channel_interpolation = False
  flat_field_correction     = False
  rate_correction           = False
  rate_correction_deadtime  = (1.23,)
  continuous_trigger_mode   = False
  single_trigger_mode       = False
  delay_before_frame        = 3.14
  gate_mode                 = False
  ngates                    = 0
  input_polarity            = 0
  output_polarity           = 0
  selected_module           = 1
  element_settings          = ('Cu',)"""
    )
    m.finalize()
    m._interface._sock.close.assert_called_once_with()


def test_mythen_configuration(beacon, run_command):
    Mythen("test", {"hostname": "mymythen", "energy": 8.88, "threshold": 4.44})
    assert run_command.commands == []
    assert run_command.setters == {"energy": "8.88", "kthresh": "4.44"}


def test_mythen_reset_configuration(beacon, run_command):
    Mythen("test", {"hostname": "mymythen", "apply_defaults": True, "gate_mode": True})
    assert run_command.commands == ["reset"]
    assert run_command.setters == {"gateen": "1"}


def test_mythen_readonly_getters(beacon, run_command):
    m = Mythen("test", {"hostname": "mymythen"})
    assert "get_version" in dir(m)
    assert m.get_version() == (3, 0, 0)


def test_mythen_commands(beacon, run_command):
    m = Mythen("test", {"hostname": "mymythen"})
    m.reset()
    m.start()
    assert list(m.readout()) == list(range(1280))
    m.stop()
    assert run_command.commands == ["reset", "start", "readout", "stop"]


def test_mythen_run(beacon, run_command):
    m = Mythen("test", {"hostname": "mymythen"})
    data = list(m.run(10, 0.1))
    assert len(data) == 10
    for frame in data:
        assert list(frame) == list(range(1280))
    assert run_command.commands == ["start"] + ["readout"] * 10 + ["stop"]
    assert run_command.setters == {"frames": "10", "time": "1000000"}


def test_mythen_counter(beacon, run_command):
    m = Mythen("test", {"hostname": "mymythen"})
    counter = m.counters.spectrum
    assert counter.name == "spectrum"
    assert counter.dtype == np.int32
    assert counter.shape == (1280,)
    assert counter._counter_controller == m


def test_mythen_from_config(run_command, beacon):
    m = beacon.get("mythen1")
    assert m.hostname == "mymythen"
    assert run_command.commands == ["reset"]


def test_mythen_ct_scan(run_command, session):
    mythen = session.config.get("mythen1")
    scan = scans.ct(0.1, mythen, return_scan=True, save=False)
    data = scan.get_data()["spectrum"]
    assert data.shape == (1, 1280)
    assert list(data[0]) == list(range(1280))


def test_mythen_default_chain_with_counter_namespace(run_command, session):
    m0 = session.config.get("m0")
    mythen = session.config.get("mythen1")
    scan = scans.ascan(m0, 0, 10, 2, 0.1, mythen, return_scan=True, save=False)
    data = scan.get_data()["spectrum"]
    assert data.shape == (3, 1280)
    assert np.array_equal(data, [list(range(1280))] * 3)
