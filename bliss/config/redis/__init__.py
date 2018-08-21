# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os


def get_redis_config_path():
    base_path, _ = os.path.split(__file__)
    return os.path.abspath(os.path.join(base_path, "redis.conf"))
