import pytest
import bliss
import gevent
from bliss.flint.helper import scan_history
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus


def test_scan_history(session, lima_simulator):
    lima = session.config.get("lima_simulator")
    # simu1 = session.config.get("simu1")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")

    # s = ascan(roby, 0, 5, 5, 0.001, diode, lima, simu1.counters.spectrum_det0)
    scan = ascan(roby, 0, 5, 5, 0.001, diode, lima)

    # the previous scan is part of the scans read from the history
    scans = scan_history.get_all_scans(bliss.current_session.name)
    node_name = scan.scan_info["node_name"]
    scan_node_names = set([s.node_name for s in scans])
    assert node_name in scan_node_names

    # scan_info read from the history is valid
    scan_info = scan_history.get_scan_info(node_name)
    assert scan_info["node_name"] == node_name

    # the data can be reached
    data = scan_history.get_data_from_redis(node_name, scan_info)
    assert "axis:roby" in data.keys()
    assert diode.fullname in data.keys()
    assert lima.image.fullname not in data.keys()
    assert len(data["axis:roby"]) == 6

    # the nexuswriter is not installed
    with pytest.raises(EnvironmentError):
        scan_history.get_data_from_file(node_name, scan_info)


def wait_scan_data_finished(scan, timeout=10):
    """
    :param bliss.scanning.scan.Scan scan:
    :param num timeout:
    """
    uris = scan_utils.scan_uris(scan)
    with gevent.Timeout(timeout):
        while uris:
            uris = [uri for uri in uris if not nexus.nxComplete(uri)]
            gevent.sleep(0.1)


def test_scan_history_with_writer(session, lima_simulator, nexus_writer_service):
    lima = session.config.get("lima_simulator")
    session.scan_saving.writer = "nexus"

    # simu1 = session.config.get("simu1")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")

    scan = ascan(roby, 0, 5, 5, 0.001, diode, lima)
    wait_scan_data_finished(scan)

    # the previous scan is part of the scans read from the history
    scans = scan_history.get_all_scans(bliss.current_session.name)
    node_name = scan.scan_info["node_name"]
    scan_node_names = set([s.node_name for s in scans])
    assert node_name in scan_node_names

    # scan_info read from the history is valid
    scan_info = scan_history.get_scan_info(node_name)
    assert scan_info["node_name"] == node_name

    # the data can be reached
    data = scan_history.get_data_from_redis(node_name, scan_info)
    assert "axis:roby" in data.keys()
    assert diode.fullname in data.keys()
    assert lima.image.fullname not in data.keys()
    assert len(data["axis:roby"]) == 6

    # the data can also be reached for the nexuswriter file
    data = scan_history.get_data_from_file(node_name, scan_info)
    assert "axis:roby" in data.keys()
    assert diode.fullname in data.keys()
    assert lima.image.fullname not in data.keys()
    assert len(data["axis:roby"]) == 6
