import random
from bliss.common.standard import *
from bliss.common.measurement import SamplingCounter
from bliss.common.session import get_current
import numpy
import gevent
from bliss.common.event import dispatcher
from bliss.scanning import scan
import math

# deactivate automatic Flint startup
SCAN_DISPLAY.auto = False


class TestScanGaussianCounter(SamplingCounter):
    def __init__(self, name, npts, center=0, stddev=1, cnt_time=0.1, low=0, upp=100):
        SamplingCounter.__init__(self, name, None)

        def gauss(x, start, end, sigma=stddev, mu=center):
            mu = (end + start) / 2.0
            sigma = (end - start) / 10.0
            h_max = 1.0 / (sigma * math.sqrt(2.0 * 3.14))
            _val = (1.0 / (sigma * math.sqrt(2.0 * 3.14))) * math.exp(
                -pow(((x - mu) / sigma), 2.0) / 2.0
            )
            noise = random.random() * 0.02
            _val = _val + noise * h_max
            return _val

        self.data = numpy.linspace(low, upp, num=npts).tolist()
        self.data = [gauss(i, low, upp) for i in self.data]
        self.i = 0
        self.cnt_time = cnt_time

    def read(self):
        gevent.sleep(self.cnt_time)
        x = self.data[self.i]
        self.i += 1
        return x


"""
Example of scan info with 1 AutoScanGaussianCounter counter

{'count_time': 0.1,
 'counters': [<AutoScanGaussianCounter object at 0x7f52b86747d0>],
 'estimation': {'total_count_time': 1.0,
                'total_motion_time': 3.100000000000001,
                'total_time': 4.100000000000001},
 'motors': [<bliss.common.scans.TimestampPlaceholder instance at 0x7f52b0b6bf38>,
            <bliss.common.axis.Axis object at 0x7f52ba679690>],
 'node_name': 'cyril:ascan_13',
 'npoints': 10,
 'other_counters': [],
 'root_path': '/tmp/scans/cyril/',
 'save': True,
 'scan_nb': 13L,
 'session_name': 'cyril',
 'sleep_time': None,
 'start': [2],
 'start_time': '2018-02-19 10:02:03.253852',
 'start_time_stamp': 1519030923.253852,
 'start_time_str': 'Mon Feb 19 10:02:03 2018',
 'stop': [3],
 'title': 'ascan simot1 2 3 10 0.1',
 'total_acq_time': 1.0,
 'type': 'ascan',
 'user_name': 'guilloud'}
"""


class AutoScanGaussianCounter(SamplingCounter):
    def __init__(self, name="autoCounter"):
        SamplingCounter.__init__(self, name, None)

        self._cnt_time = 0
        self.i = 0
        self._in_a_scan = False

        # Connect scan events.
        #                  cb function          event_name   event_source_filter
        dispatcher.connect(self.__on_scan_new, "scan_new", scan)

    def close(self):
        dispatcher.disconnect(self.__on_scan_new, "scan_new", scan)

    def __on_scan_new(self, scan_info):
        # ! also called on a "ct"

        # pprint.pprint(scan_info)

        self._cnt_time = scan_info.get("count_time")
        if self._cnt_time is None:
            self._in_a_scan = False
            return
        self._point_count = scan_info["npoints"]

        if scan_info["type"] in ["ct", "timescan"]:
            self._in_a_scan = False
        elif scan_info["type"] in ["pointscan"]:
            self._in_a_scan = True
            self._start = scan_info["start"]
            self._stop = scan_info["stop"]
        else:
            self._in_a_scan = True
            self._start = scan_info["start"][0]
            self._stop = scan_info["stop"][0]

    # scipy is not in BLISS requirements ?
    def gauss(self, x, start, end):
        mu = (end + start) / 2.0
        sigma = (end - start) / 10.0
        h_max = 1.0 / (sigma * math.sqrt(2.0 * 3.14))
        _val = (1.0 / (sigma * math.sqrt(2.0 * 3.14))) * math.exp(
            -pow(((x - mu) / sigma), 2.0) / 2.0
        )
        noise = random.random() * 0.02
        _val = _val + noise * h_max

        return _val

    def prepare(self):
        if self._in_a_scan:
            self.i = 0
            self.data = numpy.linspace(
                self._start, self._stop, num=self._point_count
            ).tolist()
            self.data = [self.gauss(i, self._start, self._stop) for i in self.data]
        else:
            pass

    def start(self):
        # print "test_setup.py : AutoScanGaussianCounter : Start Sampling counter--------------------------------"
        pass

    def stop(self):
        # print "test_setup.py : AutoScanGaussianCounter : Stop Sampling counter---------------------------------"
        pass

    def read(self):
        if self._in_a_scan:
            gevent.sleep(self._cnt_time)
            x = self.data[self.i]
            self.i += 1
            return x
        else:
            return random.random()


load_script("script1")

SESSION_NAME = get_current().name

# Do not remove this print (used in tests)
print("TEST_SESSION INITIALIZED")
#
