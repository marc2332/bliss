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

from .import release

__version__ = release.version
__author__ = release.author
__license__ = release.license
version_info = release.version_info

from gevent import monkey
monkey.patch_all(thread=False)
