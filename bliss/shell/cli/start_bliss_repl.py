# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
from bliss.shell.cli.repl import embed
from bliss import get_current_session, global_map
from bliss import logging_startup
import logging


def main(global_map=global_map):
    session_name = sys.argv[1]

    # initialize logging
    log_level = getattr(logging, sys.argv[2].upper())
    logging_startup(log_level)

    embed(
        session_name=session_name,
        use_tmux=True,
        expert_error_report=sys.argv[3] == "1" if len(sys.argv) > 3 else False,
    )
    get_current_session().close()
    global_map.clear()


if __name__ == "__main__":
    main()
