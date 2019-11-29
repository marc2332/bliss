# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common import measurementgroup
from bliss import setup_globals
from bliss.common import scans
from bliss.shell.standard import info
from bliss.scanning import toolbox
from bliss.controllers import counter
from bliss.common.counter import Counter

# 3 measurement groups : test_mg MG1 MG2 are configured
# in tests/test_configuration/sessions/test.yml


def test_mg(session):
    measurementgroup.set_active_name("test_mg")
    current_mg = getattr(setup_globals, "ACTIVE_MG")
    test_mg = getattr(setup_globals, "test_mg")
    all_MGs = ["test_mg", "MG1", "MG2"].sort()
    assert measurementgroup.get_all_names().sort() == all_MGs
    test_mg.set_active()
    assert current_mg.name == "test_mg"


def test_active_MG(session):
    measurementgroup.set_active_name("test_mg")

    assert measurementgroup.get_active_name() == "test_mg"

    # pathologic case : current MG does not exist anymore.
    delattr(setup_globals, "test_mg")
    delattr(setup_globals, "MG1")

    assert measurementgroup.get_active_name() == "test_mg"
    assert measurementgroup.get_active().name == "MG2"

    # pathologic case : no more MG is defined in the session.
    delattr(setup_globals, "MG2")

    assert measurementgroup.get_active_name() == "MG2"  # set by previous get_active()
    assert measurementgroup.get_active() is None

    # Activation of an unexisting MG raises ValueError.
    with pytest.raises(ValueError):
        measurementgroup.set_active_name("fdsfs")
    with pytest.raises(ValueError):
        measurementgroup.set_active_name(None)

    # ct must fail because there is no more default MG
    with pytest.raises(ValueError):
        scans.ct(0.1)


def test_mg_states(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = getattr(setup_globals, "ACTIVE_MG")
    # default state is 'default'.
    assert default_mg.active_state_name == "default"
    # create another state named 'state2' and use it.
    default_mg.switch_state("state2")
    assert default_mg.state_names == ["default", "state2"]
    assert default_mg.active_state_name == "state2"
    # no more counter active in this state.
    default_mg.disable("diode")
    assert list(default_mg.enabled) == []
    # back to 'default' with 'diode' counter enabled.
    default_mg.switch_state("default")
    assert default_mg.active_state_name == "default"
    assert list(default_mg.enabled) == ["diode"]
    # delete a state which is not used.
    default_mg.switch_state("state3")
    default_mg.remove_states("state2")
    assert default_mg.state_names.sort() == ["default", "state3"].sort()
    # delete current 'state3' state -> must switch to 'default'
    default_mg.remove_states("state3")
    assert default_mg.active_state_name == "default"


def test_mg_enable_disable(session, beacon):
    measurementgroup.set_active_name("MG1")  # use MG1 as active MG
    default_mg = getattr(setup_globals, "ACTIVE_MG")
    counters_list = ["diode", "diode2", "diode3"].sort()
    assert default_mg.name == "MG1"
    assert list(default_mg.available).sort() == counters_list
    # disable a single counter by name
    default_mg.disable("diode")
    assert list(default_mg.enabled).sort() == ["diode2", "diode3"].sort()
    assert list(default_mg.disabled) == ["diode"]
    default_mg.enable("diode")
    default_mg.disable("fsdf")
    # disable a list of counters by names
    default_mg.disable("diode2", "diode3")
    assert list(default_mg.enabled) == ["diode"]
    assert list(default_mg.disabled).sort() == counters_list
    cnt_diode3 = beacon.get("diode3")
    default_mg.disable_all()
    default_mg.enable_all()
    assert list(default_mg.disabled).sort() == counters_list


def test_scan(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = getattr(setup_globals, "ACTIVE_MG")
    default_mg.enable_all()
    scans.ct(0.1)

    default_mg.disable_all()

    # ct must fail because of no counter enabled.
    with pytest.raises(ValueError):
        scans.ct(0.1)

    default_mg.enable_all()


def test_print(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = getattr(setup_globals, "ACTIVE_MG")
    repr_string = "MeasurementGroup: test_mg (state='default')\n  - Existing states : 'default'\n\n  Enabled  Disabled\n  -------  -------\n  diode    \n"
    assert info(default_mg) == repr_string


def test_exceptions(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = getattr(setup_globals, "ACTIVE_MG")

    with pytest.raises(ValueError):
        measurementgroup.MeasurementGroup("foo", {"counters": None})

    with pytest.raises(ValueError):
        default_mg.remove_states("default")


def test_add(session, capsys):
    measurementgroup.set_active_name("test_mg")
    default_mg = getattr(setup_globals, "ACTIVE_MG")
    default_mg.enable_all()
    assert default_mg.enabled == {"diode"}
    try:
        default_mg.add("diode2")
        assert set(default_mg.enabled) == set(["diode", "diode2"])
        config_file = default_mg._MeasurementGroup__config
        config_file.pprint()
        captured = capsys.readouterr()
        assert "diode2" in captured.out
        default_mg.remove("diode2")
        assert default_mg.available == {"diode"}
        config_file.pprint()
        captured = capsys.readouterr()
        assert "diode2" not in captured.out
        default_mg.add("diode2")
        default_mg.disable("diode2")
        assert default_mg.disabled == {"diode2"}
        default_mg.remove("diode2")
        assert not default_mg.disabled
        assert default_mg.available == {"diode"}
        config_file.pprint()
        captured = capsys.readouterr()
        assert "diode2" not in captured.out
    finally:
        default_mg.remove("diode2")


def test_counter_group(beacon, session, lima_simulator):
    lima_simulator = beacon.get("lima_simulator")
    simu_name = lima_simulator.name
    # build a local measurementgroup
    mg = measurementgroup.MeasurementGroup("local", {"counters": [f"{simu_name}:bpm"]})
    counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(counters) == set(lima_simulator.bpm.counters)


def test_counters_with_no_register_controller(clean_gevent):
    clean_gevent["end-check"] = False

    class MyCounter(counter.CounterController):
        def __init__(self):
            super().__init__("test_cnt")
            self._counters = {
                "bla": Counter("bla", self),
                "truc": Counter("truc", self),
            }

    container = MyCounter()
    mg = measurementgroup.MeasurementGroup("local", {"counters": ["test_cnt:truc"]})
    counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(counters) == set([container._counters["truc"]])

    mg = measurementgroup.MeasurementGroup(
        "local",
        {"counters": [f"test_cnt:{name}" for name in container._counters.keys()]},
    )
    counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(counters) == set(container.counters)

    mg = measurementgroup.MeasurementGroup("local", {"counters": ["test_cnt"]})
    counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(counters) == set(container.counters)


def test_counters_with_register_counters(clean_gevent):
    clean_gevent["end-check"] = False

    class MyCounter(counter.CounterController):
        def __init__(self):
            super().__init__("test_cnt")

    class Cnt(Counter):
        def __init__(self, name, controller):
            super().__init__(name, controller)

    container = MyCounter()
    counters = {name: Cnt(name, container) for name in ["bla", "truc", "yo"]}
    container._counters = counters

    mg = measurementgroup.MeasurementGroup("local", {"counters": ["test_cnt"]})
    selected_counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(selected_counters) == set(counters.values())

    names = ["bla", "truc"]
    mg = measurementgroup.MeasurementGroup("local", {"counters": names})
    selected_counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(selected_counters) == set([counters[name] for name in names])

    fullnames = [x.fullname for x in selected_counters]
    mg = measurementgroup.MeasurementGroup("local", {"counters": fullnames})
    selected_counters = toolbox._get_counters_from_measurement_group(mg)
    assert set(selected_counters) == set([counters[name] for name in names])


names = ["bla", "truc", "yo"]


@pytest.mark.parametrize(
    "mg_counters, expected_counter_names",
    [
        (["test_cnt"], [f"test_cnt:{name}" for name in names]),
        (["test_cnt:bla", "test_cnt:truc"], ["test_cnt:bla", "test_cnt:truc"]),
    ],
    ids=["all", "partial"],
)
def test_dynamic_counters_with_register_counters(
    clean_gevent, mg_counters, expected_counter_names
):
    clean_gevent["end-check"] = False

    class Cnt(Counter):
        def __init__(self, name, controller):
            super().__init__(name, controller)

    class MyCounter(counter.CounterController):
        def __init__(self):
            super().__init__("test_cnt")

        @property
        def counters(self):
            return counter.counter_namespace((Cnt(name, self) for name in names))

    container = MyCounter()
    mg = measurementgroup.MeasurementGroup("local", {"counters": mg_counters})
    selected_counters = toolbox._get_counters_from_measurement_group(mg)
    assert set([c.fullname for c in selected_counters]) == set(expected_counter_names)


mg_lima_counters = ["lima", "lima:bpm", "lima:roi_counters"]
mg_diode_counters = ["diode1", "diode2", "diode3"]


@pytest.mark.parametrize(
    "patterns, expected_counters",
    [
        (["lima:*"], mg_lima_counters[1:]),
        (["diode[1-2]"], mg_diode_counters[:2]),
        (["lima*"], mg_lima_counters),
        (["diode1", "diode2", "lima"], mg_diode_counters[:2] + ["lima"]),
        (["diode1", "lima:*"], mg_lima_counters[1:] + ["diode1"]),
    ],
    ids=["lima:*", "diode[1-2]", "lima*", "existing_names", "mix"],
)
def test_enable_pattern(beacon, patterns, expected_counters):
    mg = measurementgroup.MeasurementGroup(
        "local", {"counters": mg_lima_counters + mg_diode_counters}
    )
    mg.disable_all()
    mg.enable(*patterns)
    assert mg.enabled == set(expected_counters)


@pytest.mark.parametrize(
    "patterns, expected_counters",
    [
        (["lima:*"], mg_lima_counters[1:]),
        (["diode[1-2]"], mg_diode_counters[:2]),
        (["lima*"], mg_lima_counters),
        (["diode1", "diode2", "lima"], mg_diode_counters[:2] + ["lima"]),
        (["diode1", "lima:*"], mg_lima_counters[1:] + ["diode1"]),
    ],
    ids=["lima:*", "diode[1-2]", "lima*", "existing_names", "mix"],
)
def test_disable_pattern(beacon, patterns, expected_counters):
    mg = measurementgroup.MeasurementGroup(
        "local", {"counters": mg_lima_counters + mg_diode_counters}
    )
    mg.disable(*patterns)
    assert mg.disabled == set(expected_counters)
