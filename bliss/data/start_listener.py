# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import time
import gevent
from bliss.data.display import ScanDataListener


def main(session_name):

    while True:
        try:
            start_time = time.time()
            sdl = ScanDataListener(session_name)
            sdl.start()
        except Exception as e:
            print(e)
            if (time.time() - start_time) < 5.0:
                gevent.sleep(5)


if __name__ == "__main__":
    main(sys.argv[1])
