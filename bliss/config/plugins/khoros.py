# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from warnings import warn

warn(
    "\nKhoros plugin is deprecated and will be removed soon. Use bliss plugin instead.",
    FutureWarning,
)

from .bliss import create_objects_from_config_node
