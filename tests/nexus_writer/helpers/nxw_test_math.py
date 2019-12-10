# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import math
import itertools
import numpy


def divisorGenerator(n, includeone=True):
    """All divisor of n
    """
    for i in range(1, int(math.sqrt(n) + 1)):
        if n % i == 0:
            if includeone or i != 1:
                yield i
            if i * i != n:
                yield n // i


def asproduct(a, n, includeone=True):
    """All tuples of length n with product a
    """
    nums = divisorGenerator(a, includeone=includeone)
    for tpl in itertools.product(nums, repeat=n):
        if numpy.product(tpl) == a:
            yield tpl
