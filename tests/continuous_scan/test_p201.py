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

from bliss.acquisition.p201 import P201AcquisitionMaster, P201AcquisitionDevice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-level', type=str, default='info',
                        help='log level (debug, info, warning, error) [default: info]')
    parser.add_argument('--nb-points', type=int,
                        help='number of points [default: 1000]', default=1000)
    parser.add_argument('--acq-time', type=float, default=1e-3,
                        help='acquisition time [default: 0.001]')
    parser.add_argument('--p201', type=str, default="p201",
                        help='P201 card configuration name [default: p201]')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    nb_points = args.nb_points
    acq_time = args.acq_time

    config = static.get_config()

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

    print "The following counters (which have software enable=True) will be used: ",
    print ", ".join(sorted(channels.keys()))

    p201_master = P201AcquisitionMaster(p201, nb_points=nb_points,
                                        acq_expo_time=acq_time)
    p201_counters = P201AcquisitionDevice(p201, nb_points=nb_points,
                                          acq_expo_time=acq_time,
                                          channels=channels)
    chain = AcquisitionChain()
    chain.add(p201_master, p201_counters)
    scan = Scan(chain, ScanRecorder())
    chain._tree.show()
    print("Prepare")
    scan.prepare()
    print("Start!")
    t = time.time()
    scan.start()
    dt = time.time() - t
    print("Finished (took %fs)!" % dt)

if __name__ == '__main__':
    main()
