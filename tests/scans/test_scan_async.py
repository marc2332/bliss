import gevent

from bliss.common import scans
from bliss.scanning.scan_saving import ScanSaving
from bliss.scanning.scan import Scan
from bliss import current_session


def test_async_demo_default(default_session, scan_tmpdir):
    # put scan file in a tmp directory
    default_session.scan_saving.base_path = str(scan_tmpdir)

    diode = default_session.config.get("diode")
    sim_ct_gauss = default_session.config.get("sim_ct_gauss")
    robz = default_session.config.get("robz")

    s1 = scans.loopscan(20, .1, diode, run=False)
    s2 = scans.ascan(robz, 0, 1, 20, .1, sim_ct_gauss, run=False)
    g1 = gevent.spawn(s1.run)
    g2 = gevent.spawn(s2.run)

    gevent.joinall([g1, g2], raise_error=True)


def test_async_custon_scan_saving(default_session, scan_tmpdir):
    # put scan file in a tmp directory
    default_session.scan_saving.base_path = str(scan_tmpdir)

    # imaging this is a complex acq procecure where I
    # want to use my own scan_saving within the procecure
    my_scan_saving = ScanSaving(current_session.name)

    diode = default_session.config.get("diode")
    sim_ct_gauss = default_session.config.get("sim_ct_gauss")
    robz = default_session.config.get("robz")

    # imagine s1 being a slow monitoring scan and s2 the real aquisition
    # this is just to simulate a more complex experimental procedure
    # where want to run a spawed scan in the background to have e.g. some temperatre values
    s1_tmp = scans.loopscan(20, .1, diode, run=False)
    s1 = Scan(s1_tmp.acq_chain, scan_saving=my_scan_saving, name="bg_scan")
    g1 = gevent.spawn(s1.run)

    s2_tmp = scans.ascan(robz, 0, .1, 10, .1, sim_ct_gauss, run=False)
    s2 = Scan(s2_tmp.acq_chain, scan_saving=my_scan_saving, name="fg_scan")
    s2.run()

    gevent.joinall([g1], raise_error=True)
    assert len(s1.get_data()["simulation_diode_sampling_controller:diode"]) == 20
    assert len(s2.get_data()["simulation_counter_controller:sim_ct_gauss"]) == 11
