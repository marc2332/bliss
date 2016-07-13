# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Bliss main package

For your convenience, configuration motion and scan APIs have been made available
directly at this level.

Here are the main bliss sub-systems:

.. autosummary::
    :nosignatures:
    :toctree:

    acquisition
    comm
    common
    config
    controllers
    data
    shell
    tango
'''

from __future__ import division

# version should be valid according to distutils.version.StrictVersion
__author__ = 'BCU (ESRF)'
__version__ = '0.1a1'
__short_version__ = '.'.join(__version__.split('.')[:2])
__license__ = 'LGPLv3'
__copyright__ = '2016 Beamline Control Unit, ESRF'
__description__ = 'BeamLine Instrumentation Support Software'

from gevent import monkey
monkey.patch_all(thread=False)

## TODO: remove those exported functions ; need changes in motor tests
from bliss.config.motors import load_cfg, load_cfg_fromstring, get_axis, get_encoder
from bliss.controllers.motor_group import Group
##
from bliss.common.scans import *
from bliss.common.standard import *
from bliss.common.continuous_scan import Scan
from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import AcquisitionDevice
from bliss.common.continuous_scan import AcquisitionMaster
from bliss.common.axis import Axis
