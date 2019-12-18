# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import global_map
from bliss.common import measurementgroup
from bliss.common import scans
from bliss.common.counter import Counter
from bliss.controllers.counter import CounterController
from bliss.shell.standard import info
from bliss.scanning import toolbox
from bliss.controllers import counter
from bliss.common.counter import Counter

# 3 measurement groups : test_mg MG1 MG2 are configured
# in tests/test_configuration/sessions/test.yml


def test_measurement_group(session):
    measurementgroup.set_active_name("test_mg")
    current_mg = session.env_dict["ACTIVE_MG"]
    test_mg = session.env_dict["test_mg"]
    all_MGs = ["test_mg", "MG1", "MG2"]
    assert set(measurementgroup.get_all_names()) == set(all_MGs)
    test_mg.set_active()
    assert current_mg.name == "test_mg"


def test_empty_session_1st_mg_default(default_session):
    assert measurementgroup.get_active() is None
    mg = measurementgroup.MeasurementGroup("test_mg", {"counters": []})
    assert measurementgroup.get_active() is mg


def test_active_mg(session):
    measurementgroup.set_active_name("test_mg")

    assert measurementgroup.get_active_name() == "test_mg"

    # TODO: removing from session env dict is not enough to clear objects from the map,
    # probably there are more references... :(
    ## pathologic case : current MG does not exist anymore.
    # del session.env_dict["test_mg"]
    # del session.env_dict["MG1"]

    # assert measurementgroup.get_active_name() == "test_mg"
    # assert measurementgroup.get_active().name == "MG2"

    # pathologic case : no more MG is defined in the session.
    # del session.env_dict["MG2"]

    # assert measurementgroup.get_active_name() == "MG2"  # set by previous get_active()
    # assert measurementgroup.get_active() is None

    # Activation of an unexisting MG raises ValueError.
    with pytest.raises(ValueError):
        measurementgroup.set_active_name("fdsfs")
    with pytest.raises(ValueError):
        measurementgroup.set_active_name(None)

    # ct must fail because there is no more default MG
    # with pytest.raises(ValueError):
    #    scans.ct(0.1)

    # the active MG did not change, finally
    assert measurementgroup.get_active_name() == "test_mg"


def test_mg_states(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = session.env_dict["ACTIVE_MG"]
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
    assert list(default_mg.enabled) == ["simulation_diode_sampling_controller:diode"]
    # delete a state which is not used.
    default_mg.switch_state("state3")
    default_mg.remove_states("state2")
    assert set(default_mg.state_names) == set(["default", "state3"])
    # delete current 'state3' state -> must switch to 'default'
    default_mg.remove_states("state3")
    assert default_mg.active_state_name == "default"


def test_mg_enable_disable(session, beacon):
    counters_list = [
        "simulation_diode_sampling_controller:diode",
        "simulation_diode_sampling_controller:diode2",
        "simulation_diode_sampling_controller:diode3",
    ]
    measurementgroup.set_active_name("MG1")  # use MG1 as active MG
    default_mg = session.env_dict["ACTIVE_MG"]
    assert default_mg.name == "MG1"
    assert set(default_mg.available) == set(counters_list)
    # disable a single counter by name
    default_mg.disable("diode")
    assert set(default_mg.enabled) == set(counters_list[1:])
    assert list(default_mg.disabled) == [counters_list[0]]
    default_mg.enable("diode")
    with pytest.raises(ValueError):
        default_mg.disable("fsdf")
    # disable a list of counters by names
    default_mg.disable("diode2", "diode3")
    assert list(default_mg.enabled) == [counters_list[0]]
    assert set(default_mg.disabled) == set(counters_list[1:])
    cnt_diode3 = beacon.get("diode3")
    default_mg.disable_all()
    default_mg.enable_all()
    assert set(default_mg.disabled) == set()
    assert set(default_mg.enabled) == set(default_mg.available)


def test_scan(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = session.env_dict["ACTIVE_MG"]
    default_mg.enable_all()
    scans.ct(0.1)

    default_mg.disable_all()

    # ct must fail because of no counter enabled.
    with pytest.raises(ValueError):
        scans.ct(0.1)

    default_mg.enable_all()


def test_print(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = session.env_dict["ACTIVE_MG"]
    repr_string = """MeasurementGroup: test_mg (state='default')
  - Existing states : 'default'

  Enabled                                     Disabled
  ------------------------------------------  ------------------------------------------
  simulation_diode_sampling_controller:diode  
"""
    assert info(default_mg) == repr_string


def test_exceptions(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = session.env_dict["ACTIVE_MG"]

    with pytest.raises(ValueError):
        measurementgroup.MeasurementGroup("foo", {"counters": None})

    with pytest.raises(ValueError):
        default_mg.remove_states("default")


def test_add_remove(session):
    measurementgroup.set_active_name("test_mg")
    default_mg = session.env_dict["ACTIVE_MG"]
    default_mg.enable_all()
    assert set(default_mg.enabled) == {"simulation_diode_sampling_controller:diode"}
    try:
        default_mg.add(session.env_dict["diode2"])
        assert set(default_mg.enabled) == set(
            [
                "simulation_diode_sampling_controller:diode2",
                "simulation_diode_sampling_controller:diode",
            ]
        )
        default_mg.remove(session.env_dict["diode2"])
        assert default_mg.available == {"simulation_diode_sampling_controller:diode"}
        default_mg.add(session.env_dict["diode2"])
        default_mg.disable("diode2")
        assert set(default_mg.disabled) == {
            "simulation_diode_sampling_controller:diode2"
        }
        default_mg.remove(session.env_dict["diode2"])
        assert not default_mg.disabled
        assert default_mg.available == {"simulation_diode_sampling_controller:diode"}

        with pytest.raises(ValueError):
            # it is forbidden to remove counter added from config
            default_mg.remove(session.env_dict["diode"])
    finally:
        try:
            default_mg.remove(session.env_dict["diode2"])
        except ValueError:
            # already removed
            pass


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
    beacon, mg_counters, expected_counter_names
):
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


@pytest.fixture
def test_mg(alias_session, lima_simulator):
    diode = alias_session.config.get("diode")
    diode2 = alias_session.config.get("diode2")
    diode3 = alias_session.config.get("diode3")
    simu1 = alias_session.config.get("simu1")

    mg = measurementgroup.MeasurementGroup(
        "local",
        {
            "counters": [
                "simulation_diode_sampling_controller:diode",
                "lima_simulator",
                "diode2",
                "diode3",
                "dtime",
            ]
        },
    )

    return mg


mg_lima_bpm_counters = [
    "lima_simulator:bpm:x",
    "lima_simulator:bpm:y",
    "lima_simulator:bpm:fwhm_x",
    "lima_simulator:bpm:fwhm_y",
    "lima_simulator:bpm:intensity",
    "lima_simulator:bpm:acq_time",
]
mg_lima_counters = mg_lima_bpm_counters + ["lima_simulator:image"]
for roi_counter in ("r1", "r2", "r3"):
    for cnt_name in ("max", "std", "min", "avg", "sum"):
        mg_lima_counters.append(f"lima_simulator:roi_counters:{roi_counter}_{cnt_name}")
mg_lima_default_counters = list(set(mg_lima_counters) - set(mg_lima_bpm_counters))
mg_diode_counters = [
    "simulation_diode_sampling_controller:diode",
    "simulation_diode_sampling_controller:diode2",
    "simulation_diode_sampling_controller:diode3",
]


@pytest.mark.parametrize(
    "patterns, expected_counters",
    [
        (["lima_simulator:*"], mg_lima_counters),
        (["diode[2-3]"], mg_diode_counters[1:]),
        (["lima*"], mg_lima_counters),
        (["lima_simulator"], mg_lima_default_counters),
        (
            ["diode", "diode2", "lima_simulator"],
            mg_diode_counters[:2] + mg_lima_default_counters,
        ),
        (
            ["diode", "lima_simulator:*"],
            mg_lima_counters + ["simulation_diode_sampling_controller:diode"],
        ),
        (
            ["dtime", "diode"],
            ["simu1:deadtime_det0", "simulation_diode_sampling_controller:diode"],
        ),
    ],
    ids=[
        "lima_simulator:*",
        "diode[2-3]",
        "lima*",
        "container",
        "existing_names",
        "mix",
        "with_alias",
    ],
)
def test_enable_disable_pattern(test_mg, patterns, expected_counters):
    test_mg.disable_all()
    assert len(test_mg.enabled) == 0
    test_mg.enable(*patterns)
    assert set(test_mg.enabled) == set(expected_counters)
    test_mg.enable_all()
    test_mg.disable(*patterns)
    assert set(test_mg.disabled) == set(expected_counters)


def test_bad_controller(test_mg):
    class BadController(CounterController):
        @property
        def counters(self):
            raise RuntimeError("Bad controller")

    bad_controller = BadController("bad_controller")
    test_mg._config_counters.append("bad_controller")

    # should work fine, even if one controller has an exception
    assert list(global_map.get_counters_iter())
    assert test_mg.available

    # try to enable non-existent controller
    with pytest.raises(ValueError):
        test_mg.enable("bad_controller")

    # try to disable non-existent counters
    with pytest.raises(ValueError):
        # explicitely test with a pattern
        test_mg.disable("bad_con*")
