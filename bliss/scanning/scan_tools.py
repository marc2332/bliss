import typeguard
from typing import Optional
from bliss.config.settings import HashSetting
from bliss.data.scan import get_counter_names
from bliss import current_session, global_map
from bliss.common.types import _countable, _scannable
from bliss.common.plot import display_motor
from bliss.scanning.scan import Scan

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


def _scan_calc(func, counter=None, axis=None, scan=None, marker=True):
    if counter is None:
        counter = get_counter(get_selected_counter_name())
    if scan is None:
        scan = current_session.scans[-1]
    res = getattr(scan, func)(counter, axis=axis, return_full_result=True)
    if marker:
        for key, value in res.items():
            if "goto" in func:
                display_motor(
                    key, scan=scan, position=value, label=func[5:] + "\n" + str(value)
                )
            else:
                display_motor(
                    key, scan=scan, position=value, label="cen\n" + str(value)
                )
                # todo: display current position if scan is last scan and axis.position != value
    if "goto" in func:
        return
    elif len(res) == 1:
        return next(iter(res.values()))
    else:
        return res


def fwhm(counter=None, axis=None, scan=None):
    return _scan_calc("fwhm", counter=counter, axis=axis, scan=scan, marker=False)


def cen(counter=None, axis=None, scan=None):
    return _scan_calc("cen", counter=counter, axis=axis, scan=scan)


@typeguard.typechecked
def goto_cen(
    counter: Optional[_countable] = None,
    axis: Optional[_scannable] = None,
    scan: Optional[Scan] = None,
):
    return _scan_calc("goto_cen", counter=counter, axis=axis, scan=scan)


def com(counter=None, axis=None, scan=None):
    return _scan_calc("com", counter=counter, axis=axis, scan=scan)


@typeguard.typechecked
def goto_com(
    counter: Optional[_countable] = None,
    axis: Optional[_scannable] = None,
    scan: Optional[Scan] = None,
):
    return _scan_calc("goto_com", counter=counter, axis=axis, scan=scan)


def peak(counter=None, axis=None, scan=None):
    return _scan_calc("peak", counter=counter, axis=axis, scan=scan)


@typeguard.typechecked
def goto_peak(
    counter: Optional[_countable] = None,
    axis: Optional[_scannable] = None,
    scan: Optional[Scan] = None,
):
    return _scan_calc("goto_peak", counter=counter, axis=axis, scan=scan)


def where():
    for axis in last_scan_motors():
        display_motor(axis)
