# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.data.display import ScanDataListener


def main(session_name, exit_read_fd=None):
    sdl = ScanDataListener(session_name, exit_read_fd)
    sdl.start()


if __name__ == "__main__":
    main(sys.argv[1])
