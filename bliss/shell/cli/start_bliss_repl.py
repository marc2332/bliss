# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.shell.cli.repl import embed


def main():
    session_name = sys.argv[1]
    embed(session_name=session_name, use_tmux=True)


if __name__ == "__main__":
    main()
