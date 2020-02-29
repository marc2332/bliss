# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.data.display import ScanDataListener


def main(session_name):
    while True:
        try:
            sdl = ScanDataListener(session_name)
            sdl.start()
        except Exception as e:
            print(e)


if __name__ == "__main__":
    main(sys.argv[1])
