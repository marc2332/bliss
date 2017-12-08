

def test_simulated_mca(beacon, mocker):
    beacon.reload()
    times = [11., 10.]
    m1 = mocker.patch('gevent.sleep')
    m2 = mocker.patch('time.time')
    m2.side_effect = times.pop
    s = beacon.get('simu1')
    a, b = s.run_single_acquisition(1.)
    assert len(a) == len(b) == 4
    assert b[0].realtime == 1.
