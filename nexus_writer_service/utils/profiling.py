try:
    import tracemalloc
    import linecache
except ImportError:
    tracemalloc = None
import cProfile
import pstats

try:
    import yappi
except ImportError:
    yappi = None
else:
    yappi.set_context_backend("greenlet")

import os
from io import StringIO
from contextlib import contextmanager, ExitStack
from time import time
from .logging_utils import log
from ..io import io_utils


DEFAULT_FILENAME = os.path.join(
    io_utils.temproot(), "pyprof_pid{}.cprof".format(os.getpid())
)


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def durationfmtcolor(x):
    if x < 0.0005:
        return bcolors.OKGREEN + ("%6dµs" % (x * 1000000)) + bcolors.ENDC
    elif x < 0.001:
        return bcolors.WARNING + ("%6dµs" % (x * 1000000)) + bcolors.ENDC
    elif x < 0.1:
        return bcolors.WARNING + ("%6dms" % (x * 1000)) + bcolors.ENDC
    else:
        return bcolors.FAIL + ("%8.3f" % x) + bcolors.ENDC


def durationfmt(x):
    if x < 0.001:
        return "%6dµs" % (x * 1000000)
    elif x < 0.1:
        return "%6dms" % (x * 1000)
    else:
        return "%8.3f" % x


@contextmanager
def execute_min_duration(func, min_duration=None):
    """Execute function when the time >= min_duration.

    :param callable func:
    :param num min_duration:
    """
    t0 = time()
    try:
        yield
    finally:
        if not min_duration or (time() - t0) >= min_duration:
            func()


def log_malloc_snapshot(snapshot, logger=None, key_type="lineno", limit=10, units="KB"):
    """
    :param tracemalloc.Snapshot snapshot:
    :param str key_type:
    :param int limit: limit number of lines
    :param str units: B, KB, MB, GB
    :param logger:
    """
    n = ["b", "kb", "mb", "gb"].index(units.lower())
    sunits, units = units, 1024 ** n

    snapshot = snapshot.filter_traces(
        (
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<unknown>"),
        )
    )
    top_stats = snapshot.statistics(key_type)
    total = sum(stat.size for stat in top_stats)

    log(logger, "================Memory profile================")
    out = ""
    for index, stat in enumerate(top_stats, 1):
        frame = stat.traceback[0]
        # replace "/path/to/module/file.py" with "module/file.py"
        # filename = os.sep.join(frame.filename.split(os.sep)[-2:])
        filename = frame.filename
        out += "\n#%s: %s:%s: %.1f %s" % (
            index,
            filename,
            frame.lineno,
            stat.size / units,
            sunits,
        )
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            out += "\n    %s" % line
        if index >= limit:
            break
    other = top_stats[index:]
    if other:
        size = sum(stat.size for stat in other)
        out += "\n%s other: %.1f %s" % (len(other), size / units, sunits)
    out += "\nTotal allocated size: %.1f %s" % (total / units, sunits)
    log(logger, out)
    log(logger, "============================================")


DEFAULT_SORTBY = "tottime"
DEFAULT_CLOCK = "cpu"


def log_pstats_snapshot(
    snapshot, logger=None, timelimit=None, sortby=None, color=False
):
    """
    :param Stats snapshot:
    :param logger:
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str sortby: sort time profile
    :param bool color:
    """
    if isinstance(sortby, str):
        sortby = [sortby]
    elif not sortby:
        sortby = [DEFAULT_SORTBY]
    for sortmethod in sortby:
        snapshot.stream = s = StringIO()
        if color:
            pstats.f8 = durationfmtcolor
        else:
            pstats.f8 = durationfmt
        ps = snapshot.sort_stats(sortmethod)
        if timelimit is None:
            timelimit = tuple()
        elif not isinstance(timelimit, tuple):
            timelimit = (timelimit,)
        ps.print_stats(*timelimit)

        log(logger, "================Time profile================")
        msg = "\n" + s.getvalue()
        log(logger, msg)
        log(logger, "============================================")


pstats_to_yappi_sort = {
    None: DEFAULT_SORTBY,
    "name": "name",
    "ncalls": "ncall",
    "cumtime": "ttot",  # including subcalls
    "tottime": "tsub",  # exluding subcalls
}


def log_yappi_snapshot(snapshot, logger=None, sortby=None):
    """
    :param YFuncStat snapshot:
    :param logger:
    :param str sortby: sort time profile
    """
    if isinstance(sortby, str):
        sortby = [sortby]
    elif not sortby:
        sortby = [DEFAULT_SORTBY]
    for sortmethod in sortby:
        s = StringIO()
        sortmethod = pstats_to_yappi_sort[sortmethod]
        snapshot = snapshot.sort(sortmethod)
        snapshot.print_all(out=s)
        log(logger, "================Time profile================")
        msg = "\n" + s.getvalue()
        log(logger, msg)
        log(logger, "============================================")


@contextmanager
def memory_context(logger=None, min_duration=None, **kwargs):
    """
    :param logger:
    :param **kwargs: see log_malloc_snapshot
    """
    if tracemalloc is None:
        log(logger, "tracemalloc required")
        return
    tracemalloc.clear_traces()
    tracemalloc.start()

    def func():
        snapshot = tracemalloc.take_snapshot()
        log_malloc_snapshot(snapshot, logger=logger, **kwargs)

    try:
        with execute_min_duration(func, min_duration=min_duration):
            yield
    finally:
        tracemalloc.stop()


@contextmanager
def time_context_cprofile(
    logger=None,
    timelimit=None,
    clock=None,
    sortby=None,
    color=False,
    filename=None,
    min_duration=None,
):
    """
    :param logger:
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str clock: always wall
    :param str sortby: sort time profile
    :param bool color:
    :param str or bool filename:
    :param num min_duration: no output when time < min_duration
    """
    pr = cProfile.Profile()
    pr.enable()

    def func():
        nonlocal filename
        snapshot = pstats.Stats(pr)
        log_pstats_snapshot(
            snapshot, logger=logger, timelimit=timelimit, sortby=sortby, color=color
        )
        if filename:
            if not isinstance(filename, str):
                filename = DEFAULT_FILENAME
            io_utils.rotatefiles(filename)
            # for pyprof2calltree
            snapshot.dump_stats(filename)
            log(logger, f"Statistics saved as {repr(filename)}")

    with execute_min_duration(func, min_duration=min_duration):
        try:
            yield
        finally:
            pr.disable()


@contextmanager
def time_context_yappi(
    logger=None,
    timelimit=None,
    clock=None,
    sortby=None,
    color=False,
    filename=None,
    min_duration=None,
    yappi_output=False,
):
    """
    :param logger:
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str clock: "wall" or "cpu"
    :param str sortby: sort time profile
    :param bool color:
    :param str or bool filename:
    :param num min_duration: no output when time < min_duration
    :param bool yappi_output: output formatted by yappi
    """
    if clock not in ("cpu", "wall"):
        clock = DEFAULT_CLOCK
    yappi.set_clock_type(clock)
    yappi.clear_stats()
    yappi.start(builtins=False)

    def func():
        nonlocal filename
        stats = yappi.get_func_stats()
        yappi.clear_stats()
        if yappi_output:
            log_yappi_snapshot(stats)
        else:
            snapshot = yappi.convert2pstats(stats)
            log_pstats_snapshot(
                snapshot, logger=logger, timelimit=timelimit, sortby=sortby, color=color
            )
        if filename:
            if not isinstance(filename, str):
                filename = DEFAULT_FILENAME
            io_utils.rotatefiles(filename)
            # callgrind: for qcachegrind
            stats.save(filename, type="callgrind")
            # for pyprof2calltree
            # snapshot.save(filename)
            log(logger, f"Statistics saved as {repr(filename)}")

    with execute_min_duration(func, min_duration=min_duration):
        try:
            yield
        finally:
            yappi.stop()


if yappi is None:
    time_context = time_context_cprofile
else:
    time_context = time_context_yappi


@contextmanager
def profile_context(
    memory=False,
    time=True,
    memlimit=10,
    timelimit=None,
    clock=None,
    sortby=None,
    color=False,
    filename=None,
    units="KB",
    logger=None,
    min_duration=None,
):
    """
    :param bool memory: profile memory usage
    :param bool time: execution time
    :param int memlimit: number of lines
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str clock: "wall" or "cpu"
    :param str sortby: sort time profile
    :param bool color:
    :param str or bool filename: dump for visual tools
    :param str units: memory units
    :param logger:
    :param num min_duration: no output when time < min_duration
    """
    with ExitStack() as stack:
        if time:
            ctx = time_context(
                timelimit=timelimit,
                clock=clock,
                sortby=sortby,
                color=color,
                filename=filename,
                logger=logger,
                min_duration=min_duration,
            )
            stack.enter_context(ctx)
        if memory:
            ctx = memory_context(
                limit=memlimit, units=units, logger=logger, min_duration=min_duration
            )
            stack.enter_context(ctx)
        yield


class ProfilerMeta(type):
    """Singleton pattern but with updating profiler arguments
    """

    _instance = None

    def __call__(cls, **kw):
        if cls._instance is None:
            cls._instance = super(ProfilerMeta, cls).__call__(**kw)
        else:
            cls._instance._kw = kw
        return cls._instance


class profile(metaclass=ProfilerMeta):
    """Singleton profile manager for time and memory profiling
    """

    def __init__(self, **kw):
        self._kw = kw
        self._ctr = 0
        self._ctx = None

    def __enter__(self):
        self._ctr += 1
        if self._ctx is None:
            self._ctx = profile_context(**self._kw)
            self._ctx.__enter__()

    def __exit__(self, *args):
        self._ctr -= 1
        if not self._ctr:
            self._ctx.__exit__(*args)
            self._ctx = None
