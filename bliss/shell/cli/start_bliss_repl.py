# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.shell.cli.repl import embed


def main():
    session_name = sys.argv[1]
    embed(session_name=session_name)


if __name__ == "__main__":
    main()
