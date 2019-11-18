import gevent

from bliss.common import scans


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
