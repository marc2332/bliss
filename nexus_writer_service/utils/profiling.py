try:
    import tracemalloc
    import linecache
except ImportError:
    tracemalloc = None
import cProfile
import pstats

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import logging
from contextlib import contextmanager


def log(logger, msg):
    """
    :param logger: `print` when `None`
    :param str msg:
    """
    if logger is None:
        print(msg)
    else:
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(msg)
        else:
            logger.info(msg)


def print_malloc_snapshot(
    snapshot, logger=None, key_type="lineno", limit=10, units="KB"
):
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


@contextmanager
def print_malloc_context(logger=None, **kwargs):
    """
    :param logger:
    :param **kwargs: see print_malloc_snapshot
    """
    if tracemalloc is None:
        log(logger, "tracemalloc required")
        return
    tracemalloc.start()
    try:
        yield
    finally:
        snapshot = tracemalloc.take_snapshot()
        print_malloc_snapshot(snapshot, logger=logger, **kwargs)


@contextmanager
def print_time_context(logger=None, timelimit=None, sortby="cumtime"):
    """
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str sortby: sort time profile
    :param logger:
    """
    pr = cProfile.Profile()
    pr.enable()
    try:
        yield
    finally:
        pr.disable()
        s = StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        if timelimit is None:
            timelimit = (0.1,)
        elif not isinstance(timelimit, tuple):
            timelimit = (timelimit,)
        ps.print_stats(*timelimit)
        log(logger, "================Time profile================")
        log(logger, "\n" + s.getvalue())
        log(logger, "============================================")


@contextmanager
def profile(
    memory=True,
    time=True,
    memlimit=10,
    timelimit=None,
    sortby="cumtime",
    units="KB",
    logger=None,
):
    """
    :param bool memory: profile memory usage
    :param bool time: execution time
    :param int memlimit: number of lines
    :param int or float timelimit: number of lines or fraction (float between 0 and 1)
    :param str sortby: sort time profile
    :param str units: memory units
    :param logger:
    """
    if not memory and not time:
        return
    elif memory and time:
        with print_time_context(timelimit=timelimit, sortby=sortby, logger=logger):
            with print_malloc_context(limit=memlimit, units=units, logger=logger):
                yield
    elif memory:
        with print_malloc_context(limit=memlimit, units=units, logger=logger):
            yield
    else:
        with print_time_context(timelimit=timelimit, sortby=sortby, logger=logger):
            yield
