# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.shell.cli.repl import embed
import logging

fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"


def main():
    session_name = sys.argv[1]
    log_level = getattr(logging, sys.argv[2].upper())

    # activate logging for module-level and session-level loggers
    logging.basicConfig(format=fmt)
    logging.getLogger("bliss").setLevel(log_level)
    logging.getLogger("beamline").setLevel(log_level)

    embed(session_name=session_name, use_tmux=True)


if __name__ == "__main__":
    main()
