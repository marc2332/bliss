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
__version__ = '0.2.dev0'
__short_version__ = '.'.join(__version__.split('.')[:2])
__license__ = 'LGPLv3'
__copyright__ = '2016 Beamline Control Unit, ESRF'
__description__ = 'BeamLine Instrumentation Support Software'

from gevent import monkey
monkey.patch_all(thread=False)
