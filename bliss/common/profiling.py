# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Execution time statistics
"""

import time
from contextlib import contextmanager
import numpy


@contextmanager
def time_profile(stats_dict, name, logger=None):
    """Add the time spend in this context to the stats dict.
    """
    try:
        call_start = time.time()
        if logger is not None:
            logger.debug("Start " + name)
        yield
    finally:
        call_end = time.time()
        stat = stats_dict.setdefault(name, list())
        stat.append((call_start, call_end))
        if logger is not None:
            logger.debug("End %s Took %fs" % (name, call_end - call_start))


def human_time_fmt(num, suffix="s"):
    """
    format time second in human readable format
    """
    for unit in ["", "m", "u", "p", "f"]:
        if abs(num) < 1:
            num *= 1000
            continue
        return "%3.3f%s%s" % (num, unit, suffix)


class Statistics:
    """
    Calculate statistics from a profiling dictionary
    key == function name
    values == list of tuple (start_time,end_time)
    """

    def __init__(self, profile):
        self._profile = {
            key: numpy.array(values, dtype=numpy.float)
            for key, values in profile.items()
        }

    @property
    def elapsed_time(self):
        """
        elapsed time function
        """
        return {
            key: values[:, 1] - values[:, 0] for key, values in self._profile.items()
        }

    @property
    def min_mean_max_std(self):
        """
        dict with (min, mean, max, std) tuple
        """
        return {
            key: (values.min(), values.mean(), values.max(), values.std())
            for key, values in self.elapsed_time.items()
        }

    def __info__(self):
        # due to recursion import standard here
        from bliss.shell.standard import _tabulate

        data = [("func_name", "min", "mean", "max", "std")]

        for key, values in sorted(
            self.min_mean_max_std.items(), key=lambda item: -item[1][1]
        ):
            data.append(
                (
                    key,
                    human_time_fmt(values[0]),
                    human_time_fmt(values[1]),
                    human_time_fmt(values[2]),
                    values[3],
                )
            )
        return _tabulate(data)
