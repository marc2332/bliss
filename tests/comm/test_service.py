from bliss.common import scans


def test_simple_counter_info(sim_ct_gauss_service):
    assert "sim_ct_gauss_service" in sim_ct_gauss_service.__info__()


def test_simple_counter_ct(session, sim_ct_gauss_service):
    s = scans.ct(0, sim_ct_gauss_service)
    data = s.get_data()
    assert all([100.] == data["sim_ct_gauss_service"])
