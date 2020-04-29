import numpy
from unittest import mock
from unittest.mock import PropertyMock
from bliss.common.scans import loopscan
from bliss.common.utils import add_property

"""
# Dark counter on P201 I0/I1
- plugin: bliss
  module: calccnt_background
  class: BackgroundCalcCounterController
  open_close: $simul_valve1
  name: p201_dark
  inputs:
    - counter: $p201.counters.I0_raw
      tags: I0_background
    - counter: $p201.counters.I1_raw
      tags: I1_background
  outputs:
    - name: I0
      tags: I0_background
    - name: I1
      tags: I1_background
"""


def test_calc_background_counter(session):
    # Test object with open_close
    simul_dark1 = session.config.get("simul_dark1")
    # Test object without open_close object
    simul_dark2 = session.config.get("simul_dark2")

    # the context manager below is needed until we have the bistate object
    with mock.patch(
        "bliss.controllers.actuator.Actuator.state", new_callable=PropertyMock
    ) as mock_state:
        mock_state.__get__ = lambda self, _, __: "CLOSED" if self.is_out() else "OPENED"

        # take background on simul_dark1
        simul_dark1.take_background()

        # TEST 1
        assert simul_dark1.background_setting["dark2"] == 12
        # TEST 2
        assert simul_dark1.background_setting["background_time"] == 1.0

    # take_background on simul_dark2
    simul_dark2.take_background(time=2.5, set_value=11.0)

    # TEST 3
    assert (
        simul_dark2.background_setting["dark1"] == 11.0
        and simul_dark2.background_setting["dark2"] == 11.0
    )

    # TEST 4
    assert simul_dark2.background_setting["background_time"] == 2.5

    # take_background on simul_dark2
    simul_dark2.take_background(time=0.5)

    # TEST 5
    assert simul_dark2.background_setting["dark2"] == 12

    # TEST 6
    assert simul_dark2.background_setting["background_time"] == 0.5

    # TEST 7
    sc = loopscan(10, 0.1, simul_dark2, save=False)
    raw_data = sc.get_data()["simul_raw1"]
    dark_data = sc.get_data()["simul_dark2_cnt1"]
    res = raw_data - (dark_data + simul_dark2.background_setting["dark1"])
    assert numpy.allclose(res, [0] * len(res))

    # take_background on p201_dark
    # p201_dark = setup_globals.p201_dark
    # p201_dark.take_background(set_value=11.11)

    # TEST 8
    # try:
    #    # get zap scan
    #    zap = setup_globals.zap
    #    sc = zap.time(100, 0.01, p201_dark)
    #    raw_data = sc.get_data()["I1_raw"]
    #    dark_data = sc.get_data()["I1"]
    #    res = raw_data - (dark_data + p201_dark.background_setting["I1_background"] * 0.01)
    #    res = np.abs(res) < 0.000001

    # TEST 9
    # print("CalcFunction - Integrating Counter         : ", end="")
    # if res.all() == True:
    #        print("PASS")
    #    else:
    #        print("FAILED")
    # except:
    #    print("zap.time                                   : ", end="")
    #    print("FAILED")
