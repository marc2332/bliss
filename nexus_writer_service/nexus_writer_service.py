# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Nexus writer service for Bliss
"""

from .tango.servers import NexusWriter
from .utils.logging_utils import getLogger, add_cli_args
from .utils.log_levels import tango_cli_slog_level, add_tango_cli_args


logger = getLogger(__name__, __file__)


def run(server, instance, log_level):
    """
    :param str server: device server name
    :param str instance: device server instance name
    :param str log_level:
    :returns Util:
    """
    verbose = tango_cli_slog_level.get(log_level, 0)
    if verbose:
        verbose = "-v{:d}".format(verbose)
        serverargs = [server, instance, verbose]
    else:
        serverargs = [server, instance]
    return NexusWriter.main(args=serverargs)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Start a Bliss session writer as a Tango server"
    )
    parser.add_argument(
        "instance",
        type=str,
        default="nexuswriters",
        help="Server instance name ('nexuswriters' by default)",
    )
    parser.add_argument(
        "--server",
        type=str,
        default="nexuswriter",
        help="Server name ('nexuswriter' by default)",
    )
    add_tango_cli_args(parser)
    add_cli_args(parser)
    args, unknown = parser.parse_known_args()
    run(args.server, args.instance, args.log_tango)


if __name__ == "__main__":
    main()
