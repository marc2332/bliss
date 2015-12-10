#!/usr/bin/python

# Simple python script to test bliss and beacon
#
# needs a ". blissrc"

from bliss.config import static
cfg = static.get_config()
ra = cfg.get("ra")
print "ra velocity : %g" % ra.velocity()


