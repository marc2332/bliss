

def test_simulated_mca_single_acquisition(beacon, mocker):
    beacon.reload()
    times = [10., 11.][::-1]
    m1 = mocker.patch('gevent.sleep')
    m2 = mocker.patch('time.time')
    m2.side_effect = times.pop
    s = beacon.get('simu1')

    a, b = s.run_single_acquisition(1.)
    assert len(a) == len(b) == 4
    assert b[0].realtime == 1.


def test_simulated_mca_external_acquisition(beacon, mocker):
    beacon.reload()
    times = [10., 10.2, 10.4, 10.6, 10.8, 11.][::-1]
    m1 = mocker.patch('gevent.sleep')
    m2 = mocker.patch('time.time')
    m2.side_effect = times.pop
    s = beacon.get('simu1')

    a, b = s.run_external_acquisition()
    assert len(a) == len(b) == 4
    assert b[0].realtime == 0.5


def test_simulated_mca_multiple_acquisitions(beacon, mocker):
    beacon.reload()
    times = [10., 14.][::-1]
    m1 = mocker.patch('gevent.sleep')
    m2 = mocker.patch('time.time')
    m2.side_effect = times.pop
    s = beacon.get('simu1')

    a, b = s.run_multiple_acquisitions(10, block_size=3)
    assert len(a) == len(b) == 10
    for i in range(10):
        assert len(a[i]) == len(b[i]) == 4
        for j in range(4):
            assert b[i][j].realtime == 0.4
