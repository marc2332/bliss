import pytest
import gevent
from bliss.common import scans, event
from bliss.scanning import scan


def test_scan_watch_callback_with_alias(alias_session):
    robyy = alias_session.env_dict["robyy"]
    dtime = alias_session.env_dict["dtime"]
    diode = alias_session.config.get("diode")
    toto = alias_session.env_dict["ALIASES"].add("toto", diode)
    event_called = gevent.event.Event()

    def on_scan_new(*args):
        pass

    def on_scan_data(scan_info, values):
        motor_channel_name = f"axis:{robyy.original_name}"
        assert toto.fullname in values
        assert dtime.fullname in values
        assert motor_channel_name in values
        event_called.set()

    def on_scan_end(*args):
        pass

    scan.set_scan_watch_callbacks(on_scan_new, on_scan_data, on_scan_end)

    s = scans.ascan(robyy, 0, 1, 2, 0.01, dtime, toto)

    with gevent.Timeout(1):
        event_called.wait()


def test_scan_info_display_names_with_alias(alias_session):
    robyy = alias_session.env_dict["robyy"]
    dtime = alias_session.env_dict["dtime"]
    diode = alias_session.config.get("diode")
    toto = alias_session.env_dict["ALIASES"].add("toto", diode)

    s = scans.ascan(robyy, 0, 1, 3, .1, dtime, toto, run=False)

    acq_chan = s.acq_chain.nodes_list[0].channels[0]
    assert acq_chan.name == "axis:robyy"
    assert (
        "axis:"
        + s.scan_info["acquisition_chain"]["axis"]["master"]["display_names"][
            acq_chan.fullname
        ]
        == acq_chan.name
    )
    dtime_chan = s.acq_chain.nodes_list[-2].channels[0]
    assert (
        s.scan_info["acquisition_chain"]["axis"]["display_names"][dtime_chan.fullname]
        == dtime_chan.name
    )
    toto_chan = s.acq_chain.nodes_list[-1].channels[0]
    assert (
        s.scan_info["acquisition_chain"]["axis"]["display_names"][toto_chan.fullname]
        == toto_chan.name
    )


def test_alias_scan_title(alias_session):
    env_dict = alias_session.env_dict

    robyy = env_dict["robyy"]
    m1 = env_dict["m1"]
    mot0 = env_dict["mot0"]
    diode = alias_session.config.get("diode")

    s = scans.ascan(robyy, 0, 1, 3, .1, diode, run=False)
    assert "ascan" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]

    s = scans.dmesh(robyy, 0, 1, 3, m1, 0, 1, 3, 0.1, diode, run=False)
    assert "dmesh" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]
    assert "m1" in s.scan_info["title"]

    s = scans.a2scan(robyy, 0, 1, m1, 0, 1, 3, 0.1, diode, run=False)
    assert "a2scan" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]
    assert "m1" in s.scan_info["title"]

    s = scans.d2scan(robyy, 0, 1, m1, 0, 1, 3, 0.1, diode, run=False)
    assert "d2scan" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]
    assert "m1" in s.scan_info["title"]

    # starting from 3, the underlying scan function is 'anscan',
    # so it does not need to test aNscan,dNscan with N>3 it is all the
    # same code
    s = scans.a3scan(robyy, 0, 1, m1, 0, 1, mot0, 0, 1, 3, 0.1, diode, run=False)
    assert "a3scan" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]
    assert "m1" in s.scan_info["title"]
    assert "mot0" in s.scan_info["title"]

    s = scans.d3scan(robyy, 0, 1, m1, 0, 1, mot0, 0, 1, 3, 0.1, diode, run=False)
    assert "d3scan" in s.scan_info["type"]
    assert "robyy" in s.scan_info["title"]
    assert "m1" in s.scan_info["title"]
    assert "mot0" in s.scan_info["title"]
