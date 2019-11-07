# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""External Nexus writer

.. autosummary::
    :toctree:

    nexus_writer_service
    session_writer
    metadata
    writers
    io
    utils
"""

import logging
from .utils import logging_utils

logger = logging.getLogger(__name__)
logging_utils.cliconfig(logger)
