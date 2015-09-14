"""
Continuous acquisition test using icepap motor and P201 card
"""
import os
import sys
import time
import logging
import argparse

import gevent

from bliss.config import static

try:
    import bliss
except ImportError:
    __this_dir = os.path.dirname(__file__)
    __juyo_dir = os.path.realpath(os.path.join(__this_dir, os.path.pardir))
    sys.path.insert(0, __juyo_dir)

from bliss.common.continuous_scan import Scan, AcquisitionChain
from bliss.common.data_manager import ScanRecorder

from bliss.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.acquisition.p201 import P201AcquisitionMaster, P201AcquisitionDevice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-level', type=str, default='info',
                        help='log level (debug, info, warning, error) [default: info]')

    parser.add_argument('--axis', type=str, default="m0",
                        help='emotion axis configuration name [default: m0]')
    parser.add_argument('--axis-nb-points', type=int, default=5,
                        help='number of points to trigger [default: 5]')
    parser.add_argument('--axis-time', type=float, default=0,
                        help='motion time (s) (excluding acceleration and ' \
                             'deceleration) [default: use currently ' \
                             ' configured velocity]')
    parser.add_argument('--axis-start-pos', type=float, default=0,
                        help='axis start position [default: 0]')
    parser.add_argument('--axis-stop-pos', type=float, default=100,
                        help='axis stop position [default: 100]')

    parser.add_argument('--p201', type=str, default="p201",
                        help='P201 card configuration name [default: p201]')
    parser.add_argument('--p201-nb-points', type=int,
                        help='number of points [default: 10]', default=10)
    parser.add_argument('--p201-acq-time', type=float, default=1e-3,
                        help='acquisition time (s) [default: 0.001]')


    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = static.get_config()

    axis = config.get(args.axis)
    p201 = config.get(args.p201)
    p201_config = config.get_config(args.p201)

    channels = {}
    for counter in p201_config.get("counters", []):
        addr = counter['address']
        enabled = counter.get('software enable', False)
        # skip internal masters and disabled channels
        if addr >= p201.COUNTERS[-2] or not enabled:
          continue
        name = counter.get('name', "c%d" % addr)
        channels[name] = addr


    emotion_master = SoftwarePositionTriggerMaster(axis, args.axis_start_pos,
                                                   args.axis_stop_pos,
                                                   args.axis_nb_points,
                                                   time=args.axis_time)
    chain = AcquisitionChain()

    p201_master = P201AcquisitionMaster(p201, nb_points=args.p201_nb_points,
                                        acq_expo_time=args.p201_acq_time)
    p201_counters = P201AcquisitionDevice(p201, nb_points=args.p201_nb_points,
                                          acq_expo_time=args.p201_acq_time,
                                          channels=channels)

    chain.add(emotion_master, p201_master)
    chain.add(p201_master, p201_counters)
    chain._tree.show()
    scan = Scan(chain, ScanRecorder())
    print("Prepare")
    scan.prepare()
    print("Start!")
    t = time.time()
    scan.start()
    dt = time.time() - t
    print("Finished (took %fs)!" % dt)

if __name__ == '__main__':
    main()
