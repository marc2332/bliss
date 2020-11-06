# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Execution time statistics
"""

import time
from io import StringIO
from contextlib import contextmanager
import numpy
import yappi
from bliss.common.logtools import user_print


yappi.set_context_backend("greenlet")
yappi.set_clock_type("wall")


yappi_to_pstats_sort = {
    "ncall": "ncalls",
    "ttot": "cumtime",  # including subcalls
    "tsub": "tottime",  # excluding subcalls
}


def print_yappi_snapshot(stats, sortby=None, filename=None, restrictions=tuple()):
    """
    :param YFuncStat stats:
    :param str sortby: tsub (excluding subs), ttot or tavg (ttot/ncalls)
    :param str filename: can be inspected with qcachegrind
    :param tuple restrictions:
    """
    if not sortby:
        sortby = "ttot"
    s = StringIO()

    # YAPPI output is limited
    # stats = stats.sort(sortby)
    # stats.print_all(out=s)
    # Therefore convert to pstats
    sortby = yappi_to_pstats_sort.get(sortby, "ttot")
    pstat = yappi.convert2pstats(stats)
    pstat.stream = s
    pstat = pstat.sort_stats(sortby)
    pstat.print_stats(*restrictions)

    user_print(s.getvalue())
    if filename:
        stats.save(filename, type="callgrind")


@contextmanager
def time_profile(*restrictions, sortby=None, filename=None):
    """
    :param restrictions: integer (number of lines)
                         float (percentage of lines)
                         str (regular expression)
    :param str sortby: tsub (excluding subcalls), ttot or tavg (ttot/ncalls)
    :param str filename: can be inspected with qcachegrind
    """
    yappi.clear_stats()
    yappi.start(builtins=True)
    try:
        yield
    finally:
        yappi.stop()
        stats = yappi.get_func_stats()
        yappi.clear_stats()
        print_yappi_snapshot(
            stats, sortby=sortby, filename=filename, restrictions=restrictions
        )


@contextmanager
def simple_time_profile(stats_dict, name, logger=None):
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


class SimpleTimeStatistics:
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
    def _sample_statistics(self):
        """
        dict with statistics tuple
        """
        return {
            key: (values.min(), values.mean(), values.max(), values.std(), values.sum())
            for key, values in self.elapsed_time.items()
        }

    def __info__(self):
        # due to recursion import standard here
        from bliss.shell.standard import _tabulate

        data = [("func_name", "min", "mean", "max", "std", "total")]

        for key, values in sorted(
            self._sample_statistics.items(), key=lambda item: -item[1][-1]
        ):
            data.append(
                (
                    key,
                    self.human_time_fmt(values[0]),
                    self.human_time_fmt(values[1]),
                    self.human_time_fmt(values[2]),
                    self.human_time_fmt(values[3]),
                    self.human_time_fmt(values[4]),
                )
            )
        return _tabulate(data)

    @staticmethod
    def human_time_fmt(num, suffix="s"):
        """
        format time second in human readable format
        """
        for unit in ["", "m", "u", "p", "f"]:
            if abs(num) < 1:
                num *= 1000
                continue
            return "%3.3f%s%s" % (num, unit, suffix)
