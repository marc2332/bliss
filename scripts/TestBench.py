#!/usr/bin/python

# Simple python script to test bliss
#
# needs a ". blissrc"

import time
import PyTango
from bliss.common import log
import bliss

log.level(log.DEBUG)
log.level(log.INFO)

from bliss.config import settings
from bliss.config.motors import set_backend
set_backend("beacon")

ra = bliss.get_axis("ra")
svg = bliss.get_axis("svg")


# ra.apply_config()
# svg.apply_config()


