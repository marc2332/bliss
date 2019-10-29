def test_simulated_mca_software_acquisition(beacon, mocker):
    times = list(range(100))[::-1]
    m1 = mocker.patch("gevent.sleep")
    m2 = mocker.patch("time.time")
    m2.side_effect = times.pop
    s = beacon.get("simu1")

    a, b = s.run_software_acquisition(10, .1)
    for i in range(10):
        assert len(a[i]) == len(b[i]) == 4
        for j in range(4):
            assert b[i][j].realtime == .1


def test_simulated_mca_gate_acquisition(beacon, mocker):
    times = list(range(30))[::-1]
    m1 = mocker.patch("gevent.sleep")
    m2 = mocker.patch("time.time")
    m2.side_effect = times.pop
    s = beacon.get("simu1")

    a, b = s.run_gate_acquisition(10)
    for i in range(10):
        assert len(a[i]) == len(b[i]) == 4
        for j in range(4):
            assert b[i][j].realtime == .5


def test_simulated_mca_multiple_acquisitions(beacon, mocker):
    times = list(range(30))[::-1]
    m1 = mocker.patch("gevent.sleep")
    m2 = mocker.patch("time.time")
    m2.side_effect = times.pop
    s = beacon.get("simu1")

    a, b = s.run_synchronized_acquisition(10, block_size=3)
    assert len(a) == len(b) == 10
    for i in range(10):
        assert len(a[i]) == len(b[i]) == 4
        for j in range(4):
            assert b[i][j].realtime == 0.4
