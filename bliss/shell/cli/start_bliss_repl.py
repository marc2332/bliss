# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.shell.cli.repl import embed
from bliss.common.logtools import logging_startup
import logging


def main():
    session_name = sys.argv[1]

    # initialize logging
    log_level = getattr(logging, sys.argv[2].upper())
    logging_startup(log_level)

    try:
        embed(
            session_name=session_name,
            use_tmux=True,
            expert_error_report=sys.argv[3] == "1",
        )
    except IndexError:
        embed(session_name=session_name, use_tmux=True, expert_error_report=False)


if __name__ == "__main__":
    main()
