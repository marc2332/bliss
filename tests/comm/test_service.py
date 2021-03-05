import subprocess
import pytest
import gevent
import sys
import os

from bliss.common import scans

SERVICE = [sys.executable, "-u", "-m", "bliss.comm.service"]


@pytest.fixture
def sim_ct_gauss_service(wait_for_fixture, wait_terminate_fixture, beacon):
    proc = subprocess.Popen(SERVICE + ["sim_ct_gauss_service"], stdout=subprocess.PIPE)
    wait_for_fixture(proc.stdout, "Starting service sim_ct_gauss_service")
    gevent.sleep(1)
    proc.stdout.close()
    sim = beacon.get("sim_ct_gauss_service")
    yield sim
    sim._rpc_connection.close()
    wait_terminate_fixture(proc)


def test_simple_counter_info(sim_ct_gauss_service):
    assert "sim_ct_gauss_service" in sim_ct_gauss_service.__info__()


def test_simple_counter_ct(session, sim_ct_gauss_service):
    s = scans.ct(0, sim_ct_gauss_service)
    data = s.get_data()
    assert all([100.] == data["sim_ct_gauss_service"])
