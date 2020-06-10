import pytest
from bliss.shell.standard import wm
from bliss import global_map

alias_dump = """Alias    Original fullname
-------  ----------------------------------
mot0     m0
robyy    roby
robzz    robz
dtime    simu1:deadtime_det0
rtime    simu1:realtime_det0
ltime    simu1:energy_livetime_det0
dtime1   simu1:deadtime_det1
dtime2   simu1:deadtime_det2
myroi    lima_simulator:roi_counters:r1_sum
myroi3   lima_simulator:roi_counters:r3_sum"""

alias_dump2 = """Alias    Original fullname
-------  ----------------------------------
mot0     m0
robyy    roby
robzz    robz
dtime    simu1:deadtime_det0
rtime    simu1:realtime_det0
ltime    simu1:energy_livetime_det0
dtime1   simu1:deadtime_det1
dtime2   simu1:deadtime_det2
myroi    lima_simulator:roi_counters:r1_sum
myroi3   lima_simulator:roi_counters:r3_sum
m22      m1"""

alias_dump3 = """Alias    Original fullname
-------  ----------------------------------
mot0     m0
robyy    roby
robzz    robz
dtime    simu1:deadtime_det0
rtime    simu1:realtime_det0
ltime    simu1:energy_livetime_det0
dtime1   simu1:deadtime_det1
dtime2   simu1:deadtime_det2
myroi    lima_simulator:roi_counters:r1_sum
myroi3   lima_simulator:roi_counters:r3_sum
m22      m1
myr2sum  lima_simulator:roi_counters:r2_sum"""


def compare_line_by_line(string1, string2):
    list1 = string1.split("\n")
    list2 = string2.split("\n")
    assert len(list1) == len(list2)
    for l1, l2 in zip(list1, list2):
        assert l1 == l2


def test_alias_env_dict(alias_session):
    env_dict = alias_session.env_dict
    assert env_dict["ALIASES"] is not None
    compare_line_by_line(env_dict["ALIASES"].list_aliases(), alias_dump)


def test_alias_add_dynamically(alias_session, lima_simulator):
    env_dict = alias_session.env_dict
    lima_simulator = env_dict["lima_simulator"]

    m0 = alias_session.config.get("m0")
    with pytest.raises(RuntimeError):
        global_map.aliases.add("m22", m0)

    m1 = alias_session.config.get("m1")
    global_map.aliases.add("m22", m1)
    assert "m22" in env_dict
    assert m1 == env_dict["m22"]

    # create roi counter
    ALIASES = env_dict["ALIASES"]
    compare_line_by_line(ALIASES.list_aliases(), alias_dump2)

    ALIASES.add("myr2sum", lima_simulator.counters.r2_sum)
    compare_line_by_line(ALIASES.list_aliases(), alias_dump3)


def test_alias_duplication(alias_session):
    env_dict = alias_session.env_dict

    with pytest.raises(RuntimeError):
        global_map.aliases.add("blabla", env_dict["robyy"])

    simu1 = alias_session.config.get("simu1")
    with pytest.raises(RuntimeError):
        global_map.aliases.add("dtime", simu1.counters.deadtime_det0)

    m0 = alias_session.config.get("m0")
    with pytest.raises(RuntimeError):
        global_map.aliases.add("m1", m0)

    with pytest.raises(RuntimeError):
        global_map.aliases.add("robyy", m0)


def test_alias_overwriting_setup_object(alias_session):
    # related to https://gitlab.esrf.fr/bliss/bliss/merge_requests/1455#note_34532
    env_dict = alias_session.env_dict

    m2 = env_dict["m2"]
    roby = alias_session.config.get("roby")

    with pytest.raises(RuntimeError):
        global_map.aliases.add("roby", m2)

    with pytest.raises(RuntimeError):
        # 'bad' is an existing object in config (but not loaded in this session)
        global_map.aliases.add("bad", m2)


def test_alias_get(alias_session):
    env_dict = alias_session.env_dict

    r = env_dict["ALIASES"].get("robyy")
    assert r is env_dict["robyy"]

    assert env_dict["ALIASES"].get("does_not_exist") is None


def test_alias_included_session(alias_session):
    env_dict = alias_session.env_dict
    assert "mot0" in global_map.aliases.names_iter()
    m0 = alias_session.config.get("m0")
    assert env_dict["mot0"] == m0


def test_alias_add_remove_set_get(alias_session):
    env_dict = alias_session.env_dict
    roby = alias_session.config.get("roby")
    assert env_dict["robyy"] == env_dict["roby"]
    ALIASES = env_dict["ALIASES"]
    assert ALIASES.get_alias("m0") == "mot0"

    with pytest.raises(RuntimeError):
        # mot0 alias already exists
        ALIASES.add("mot0", env_dict["lima_simulator"].counters.x)

    try:
        ALIASES.remove("mot0")
        ALIASES.remove("robyy")

        assert env_dict.get("mot0") is None
        assert env_dict.get("m0") is None  # aliased object has never been there

        ALIASES.add("mot0", roby)

        assert env_dict.get("roby") is None
        assert ALIASES.get("mot0") == roby
    finally:
        ALIASES.set("mot0", "m0")


def test_alias_original_object_removal(alias_session):
    env_dict = alias_session.env_dict
    ALIASES = env_dict["ALIASES"]

    assert "roby" not in env_dict  # only robyy is there

    diode = alias_session.config.get("diode")

    assert "diode" in env_dict

    # add alias with object
    ALIASES.add("dd", diode)

    assert "dd" in env_dict
    assert "diode" not in env_dict

    ALIASES.remove("dd")

    diode = alias_session.config.get("diode")
    # add alias with name
    ALIASES.add("dd", diode)
    assert "dd" in env_dict
    assert "diode" not in env_dict

    # check with a counter within a controller
    ALIASES.add("x", "lima_simulator:bpm:x")
    lima_simulator = env_dict["lima_simulator"]
    assert env_dict["x"] == lima_simulator.counters.x


def test_alias_wm(alias_session, capsys):
    robyy = alias_session.env_dict["robyy"]

    wm(robyy)

    output = capsys.readouterr()[0]
    assert "robyy" in output
    assert "inf" in output
