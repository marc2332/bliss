import pytest


def test_wagogroup_get(default_session, wago_mockup):
    wago = default_session.config.get("wago_simulator")
    wago_group = default_session.config.get("wago_group")
    for key in wago_group.logical_keys:
        assert wago_group.get(key) == wago.get(key)


def test_wagogroup_set(default_session, wago_mockup, clean_gevent):
    clean_gevent["end-check"] = False

    wago = default_session.config.get("wago_simulator")
    wago_group = default_session.config.get("wago_group")
    wago_group.set("foh2ctrl", 1, 1, 1, 1, "o10v1", -4.0)
    assert wago_group.get("foh2ctrl") == [1, 1, 1, 1]
    assert wago.get("foh2ctrl") == [1, 1, 1, 1]
    assert wago_group.get("o10v1") == pytest.approx(-4.0, .001)
    assert wago.get("o10v1") == pytest.approx(-4.0, .001)


def test_wagogroup_counters(default_session, wago_mockup, clean_gevent):
    """
    check if you can define a wago key as a counter in config and read it
    """
    clean_gevent["end-check"] = False
    wago_group = default_session.config.get("wago_group")
    assert len(wago_group.counters) == 2
    assert isinstance(wago_group.read_all(wago_group.esTr1)[0], float)
    assert len(wago_group.read_all(*wago_group.counters)) == 2
