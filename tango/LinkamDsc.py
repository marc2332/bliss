#!/usr/bin/env python

import sys

sys.argv[0] = "LinkamDsc"

if len(sys.argv) == 1:
    # no args ? -> I add "-?" to show defined instances.
    sys.argv.append("-?")

from bliss.tango.servers.linkamdsc_ds import main
main()