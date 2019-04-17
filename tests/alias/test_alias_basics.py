import pytest
from bliss.common import scans

alias_dump = """Alias    Original name                       Linked to py obj
-------  ----------------------------------  ------------------
robyy    roby                                True
robzz    robz                                True
dtime    simu1.deadtime_det0                 True
rtime    simu1.realtime_det0                 True
ltime    simu1.livetime_det0                 True
myroi    lima_simulator.roi_counters.r1.sum  False"""

alias_dump2 = """Alias    Original name                       Linked to py obj
-------  ----------------------------------  ------------------
robyy    roby                                True
robzz    robz                                True
dtime    simu1.deadtime_det0                 True
rtime    simu1.realtime_det0                 True
ltime    simu1.livetime_det0                 True
myroi    lima_simulator.roi_counters.r1.sum  False
myroi3   lima_simulator.roi_counters.r3.sum  True
m22      m0                                  True"""

alias_dump3 = """Alias    Original name                       Linked to py obj
-------  ----------------------------------  ------------------
robyy    roby                                True
robzz    robz                                True
dtime    simu1.deadtime_det0                 True
rtime    simu1.realtime_det0                 True
ltime    simu1.livetime_det0                 True
myroi    lima_simulator.roi_counters.r1.sum  False
myroi3   lima_simulator.roi_counters.r3.sum  True
m22      m0                                  True
myr2sum  lima_simulator.roi_counters.r2.sum  True"""


def compare_line_by_line(string1, string2):
    list1 = string1.split("\n")
    list2 = string2.split("\n")
    assert len(list1) == len(list2)
    for l1, l2 in zip(list1, list2):
        assert l1 == l2


def test_alias_env_dict(beacon, lima_simulator):
    env_dict = dict()
    session = beacon.get("test_alias")
    session.setup(env_dict)
    assert env_dict["ALIASES"] is not None
    compare_line_by_line(env_dict["ALIASES"]._list_aliases(), alias_dump)
    session.close()


def test_alias_add_dynamically(alias_session):

    env_dict, session = alias_session

    m0 = session.config.get("m0")
    m0.set_alias("m22")

    assert "m22" in env_dict
    assert env_dict["m22"].has_alias
    assert env_dict["m22"].alias_or_name == "m22"
    assert env_dict["m22"].name == "m0"
    assert m0.alias_object.has_object_ref

    ALIASES = env_dict["ALIASES"]
    compare_line_by_line(ALIASES._list_aliases(), alias_dump2)

    ALIASES.create_alias("myr2sum", "lima_simulator.roi_counters.r2.sum")
    compare_line_by_line(ALIASES._list_aliases(), alias_dump3)


def test_alias_duplication(alias_session):

    env_dict, session = alias_session

    with pytest.raises(RuntimeError):
        env_dict["robyy"].set_alias("blabla")

    m0 = session.config.get("m0")
    with pytest.raises(RuntimeError):
        m0.set_alias("m1")

    with pytest.raises(RuntimeError):
        m0.set_alias("robyy")


def test_alias_get(alias_session):

    env_dict, session = alias_session

    r = env_dict["ALIASES"].get("robyy")
    assert r is env_dict["robyy"]

    with pytest.raises(RuntimeError):
        r = env_dict["ALIASES"].get("does_not_exist")

    with pytest.raises(ValueError):
        r = env_dict["ALIASES"].get("myroi")


def test_scan_info_display_names_with_alias(alias_session):

    env_dict, session = alias_session
    robyy = env_dict["ALIASES"].get("robyy")
    diode = session.config.get("diode")
    s = scans.ascan(robyy, 0, 1, 3, .1, diode, run=False)
    assert (
        s.scan_info["acquisition_chain"]["axis"]["master"]["display_names"]["axis:roby"]
        == "robyy"
    )
