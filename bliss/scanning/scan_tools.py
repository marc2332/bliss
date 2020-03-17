import typeguard
from typing import Optional, List
from bliss.config.settings import HashSetting
from bliss.data.scan import get_counter_names
from bliss import current_session, global_map
from bliss.common.types import _countable, _scannable
from bliss.common.axis import Axis
from bliss.scanning.scan import ScanDisplay

import gevent

"""
Alignment Helpers: cen peak com that interact with plotselect 
and work outside of the context of a scan while interacting
with the last scan.
"""


@typeguard.typechecked
def get_counter(counter_name: str):
    """
    Gets a counter instance from a counter name
    """
    for _counter in global_map.get_counters_iter():
        if _counter.fullname == counter_name:
            return _counter
    raise RuntimeError("Can't find the counter")


def get_selected_counter_name(counter=None):
    """
    Returns the name of the counter selected *in flint*.

    Returns ONLY ONE counter.

    Raises RuntimeError if more than one counter is selected.

    Used to determine which counter to use for cen pic curs functions.
    """
    if not current_session.scans:
        raise RuntimeError("Scans list is empty!")
    scan_counter_names = set(get_counter_names(current_session.scans[-1]))
    plot_select = HashSetting("%s:plot_select" % current_session.name)
    selected_flint_counter_names = set(plot_select.keys())
    alignment_counts = scan_counter_names.intersection(selected_flint_counter_names)
    if not alignment_counts:
        raise RuntimeError(
            "No counter selected...\n"
            "Hints: Use flint or plotselect to define which counter to use for alignment"
        )
    elif len(alignment_counts) > 1:
        if counter is None:
            raise RuntimeError(
                "There is actually several counter selected (%s).\n"
                "Only one should be selected.\n"
                "Hints: Use flint or plotselect to define which counter to use for alignment"
                % alignment_counts
            )
        if counter.name in alignment_counts:
            return counter.name
        else:
            raise RuntimeError(
                f"Counter {counter.name} is not part of the last scan.\n"
            )

    return alignment_counts.pop()


def last_scan_motor(axis=None):
    """
    Return the last motor used in the last scan
    """
    if not len(current_session.scans):
        raise RuntimeError("No scan available. Hint: do at least one ;)")
    scan = current_session.scans[-1]
    axis_name = scan._get_data_axis_name(axis=axis)
    return current_session.env_dict[axis_name]


def last_scan_motors():
    """
    Return a list of motor used in the last scan
    """
    if not len(current_session.scans):
        raise RuntimeError("No scan available. Hint: do at least one ;)")
    scan = current_session.scans[-1]
    axes_name = scan._get_data_axes_name()
    return [current_session.env_dict[axis_name] for axis_name in axes_name]


def get_channel_names(*objs) -> List[str]:
    """
    ?? returns a list containing aqc-channels names produced by provieded objects??
    # FIXME: For now only counters and axis are supported.
    """
    result: List[str] = []
    for obj in objs:
        # An object could contain many channels?
        channel_names: List[str] = []
        if isinstance(obj, str):
            alias = global_map.aliases.get(obj)
            if alias is not None:
                channel_names = get_channel_names(alias)
            else:
                channel_names = [obj]
        elif isinstance(obj, Axis):
            channel_names = ["axis:%s" % obj.name]
        elif hasattr(obj, "fullname"):
            # Assume it's a counter
            channel_names = [obj.fullname]
        else:
            # FIXME: Add a warning
            pass
        result.extend(channel_names)
    return result


def cen(counter=None, axis=None):
    if counter is None:
        counter = get_counter(get_selected_counter_name())
    return current_session.scans[-1].cen(counter, axis=axis)


@typeguard.typechecked
def goto_cen(counter: Optional[_countable] = None, axis: Optional[_scannable] = None):
    if not counter:
        counter = get_counter(get_selected_counter_name())

    return current_session.scans[-1].goto_cen(counter, axis=axis)


def com(counter=None, axis=None):
    if counter is None:
        counter = get_counter(get_selected_counter_name())
    return current_session.scans[-1].com(counter, axis=axis)


@typeguard.typechecked
def goto_com(counter: Optional[_countable] = None, axis: Optional[_scannable] = None):
    if not counter:
        counter = get_counter(get_selected_counter_name())

    return current_session.scans[-1].goto_com(counter, axis=axis)


def peak(counter=None, axis=None):
    if counter is None:
        counter = get_counter(get_selected_counter_name())
    return current_session.scans[-1].peak(counter, axis=axis)


@typeguard.typechecked
def goto_peak(counter: Optional[_countable] = None, axis: Optional[_scannable] = None):
    if not counter:
        counter = get_counter(get_selected_counter_name())

    return current_session.scans[-1].goto_peak(counter, axis=axis)

    scan = current_session.scans[-1]

    return scan.goto_peak(counter, axis=axis)


def where():
    for axis in last_scan_motors():
        current_session.scans[-1].where(axis=axis)
