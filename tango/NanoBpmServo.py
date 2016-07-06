#!/usr/bin/env python

import sys

sys.argv[0] = "NanoBpmServo"

if len(sys.argv) == 1:
    # no args ? -> I add "-?" to show defined instances.
    sys.argv.append("-?")

from bliss.tango.servers.nanobpm_servo_ds import main
main()