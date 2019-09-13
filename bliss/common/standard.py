# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Standard bliss macros (:func:`~bliss.common.standard.wa`, \
:func:`~bliss.common.standard.mv`, etc)
"""
import contextlib
import time
from bliss.common import timedisplay

from bliss import global_map, global_log
from bliss.common import scans
from bliss.common.scans import *
from bliss.common.plot import plot
from bliss.scanning.scan import SCANS
from bliss.common.soft_axis import SoftAxis
from bliss.common.measurement import SoftCounter
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common import logtools
from bliss.common.logtools import *

import sys

__all__ = (
    [
        "wa",
        "wm",
        "sta",
        "stm",
        "mv",
        "umv",
        "mvr",
        "umvr",
        "move",
        "plotselect",
        "prdef",
        "sync",
        "lslog",
        "lsdebug",
        "debugon",
        "debugoff",
        "info",
        "bench",
    ]
    + scans.__all__
    + logtools.__all__
    + ["cleanup", "error_cleanup", "plot", "lscnt"]
    + ["SoftAxis", "SoftCounter", "edit_roi_counters"]
)

import inspect
import logging
import functools
import itertools
import linecache
import collections.abc

from gevent import sleep
from tabulate import tabulate

tabulate.PRESERVE_WHITESPACE = True


from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

from bliss import setup_globals
from bliss.common.motor_group import Group
from bliss.common.utils import safe_get, ErrorWithTraceback
from bliss.common.measurement import BaseCounter

_ERR = "!ERR"
_MAX_COLS = 9
_MISSING_VAL = "-----"
_FLOAT_FORMAT = ".05f"


_log = logging.getLogger("bliss.standard")


def lslog(glob: str = None, debug_only=False) -> None:
    """
    Search for loggers
    Args:
        glob: a logger name with optional glob matching
        debug_only: True to display only loggers at debug level 
                    (equivalent to lslog)


    Hints on glob: pattern matching normally used by shells
                    common operators are * for any number of characters
                    and ? for one character of any type
    Examples:

        >>> lslog()  # prints all loggers

        >>> lslog('*motor?')  # prints loggers that finish with 'motor' + 1 char
                              # like motor1, motor2, motork

        >>> lslog('*Socket*')  # prints loggers that contains 'Socket'

    """
    if glob is None:
        loggers = {
            **global_log._find_loggers("bliss*"),
            **global_log._find_loggers("global*"),
        }
    else:
        loggers = global_log._find_loggers(glob)
    if loggers.items():
        maxlen = max([len(name) for name, _ in loggers.items()])
    else:
        maxlen = 0
    msgfmt = "{0:{width}} {1:8}"
    output = False

    for name in sorted(loggers.keys()):
        logger = loggers[name]
        try:
            has_debug = logger.getEffectiveLevel() == logging.DEBUG
        except AttributeError:
            has_debug = False
        if debug_only and not has_debug:
            continue
        if not output:
            output = True
            print("\n" + msgfmt.format("logger name", "level", width=maxlen))
            print(msgfmt.format("=" * maxlen, 8 * "=", width=maxlen))
        print(
            msgfmt.format(
                name, logging.getLevelName(logger.getEffectiveLevel()), width=maxlen
            )
        )
    if output:
        print("")
    else:
        print("No loggers found.\n")


def lsdebug(glob: str = None, debug_only=False) -> None:
    """
    Displays current Loggers at DEBUG level
    """
    lslog(glob, debug_only=True)


def debugon(glob_logger_pattern_or_obj) -> None:
    """
    Activates debug-level logging for a specifig logger or an object

    Args:
        glob_logger_pattern_or_obj: glob style pattern matching for logger name, or instance

    Hints on glob: pattern matching normally used by shells
                   common operators are * for any number of characters
                   and ? for one character of any type

    Returns:
        None

    Examples:
        >>> log.debugon('*motorsrv')
        Set logger [motorsrv] to DEBUG level
        Set logger [motorsrv.Connection] to DEBUG level
        >>> log.debugon('*rob?')
        Set logger [session.device.controller.roby] to DEBUG level
        Set logger [session.device.controller.robz] to DEBUG level
    """
    activated = global_log.debugon(glob_logger_pattern_or_obj)
    if activated:
        for name in activated:
            print(f"Setting {name} to show debug messages")
    else:
        print(f"NO loggers found for [{glob_logger_pattern_or_obj}]")


def debugoff(glob_logger_pattern_or_obj):
    deactivated = global_log.debugoff(glob_logger_pattern_or_obj)
    if deactivated:
        for name in deactivated:
            print(f"Setting {name} to hide debug messages")
    else:
        print(f"NO loggers found for [{glob_logger_pattern_or_obj}]")


def _tabulate(data, **kwargs):
    kwargs.setdefault("headers", "firstrow")
    kwargs.setdefault("floatfmt", _FLOAT_FORMAT)
    kwargs.setdefault("numalign", "right")

    return str(tabulate(data, **kwargs))


def __pyhighlight(code, bg="dark", outfile=None):
    formatter = TerminalFormatter(bg=bg)
    return highlight(code, PythonLexer(), formatter, outfile=outfile)


def _print_errors_with_traceback(errors, device_type="motor"):
    """ RE-raise caught errors with original traceback """
    for (label, error_with_traceback_obj) in errors:
        exc_type, exc_val, exc_tb = error_with_traceback_obj.exc_info
        try:
            # we re-raise in order to pass the motor label to the error msg
            # else calling sys.excepthook(*sys.exc_info()) would be fine
            raise exc_type(
                f"Error on {device_type} '{label}': {str(exc_val)}"
            ).with_traceback(exc_tb)
        except:
            sys.excepthook(*sys.exc_info())


def sync(*axes):
    """
    Forces axes synchronization with the hardware

    Args:
        axes: list of axis objects or names. If no axis is given, it syncs all
              all axes present in the session
    """
    if axes:
        axes = global_map.get_axis_objects_iter(*axes)
    else:
        axes = global_map.get_axes_iter()
    for axis in axes:
        axis.sync_hard()


def wa(**kwargs):
    """
    Displays all positions (Where All) in both user and dial units
    """
    max_cols = kwargs.get("max_cols", _MAX_COLS)
    err = kwargs.get("err", _ERR)

    print("Current Positions: user")
    print("                   dial")
    header, pos, dial = [], [], []
    tables = [(header, pos, dial)]
    errors = []
    try:
        for (
            axis_name,
            position,
            dial_position,
            axis_unit,
        ) in global_map.get_axes_positions_iter(
            on_error=ErrorWithTraceback(error_txt=err)
        ):
            if len(header) == max_cols:
                header, pos, dial = [], [], []
                tables.append((header, pos, dial))
            axis_label = axis_name
            if axis_unit:
                axis_label += "[{0}]".format(axis_unit)
            header.append(axis_label)

            pos.append(position)
            dial.append(dial_position)

            if _ERR in [str(position), str(dial_position)]:
                errors.append((axis_label, dial_position))

        for table in tables:
            print("")
            print(_tabulate(table))

        _print_errors_with_traceback(errors, device_type="motor")

    finally:
        errors.clear()


def wm(*axes, **kwargs):
    """
    Displays information (position - user and dial, limits) of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis

    example:
      DEMO [18]: wm(m2, m1, m3)

                       m2      m1[mm]       m3
      -------  ----------  ----------  -------
      User
       High     -123.00000   128.00000      inf
       Current   -12.00000     7.00000  3.00000
       Low       456.00000  -451.00000     -inf
      Offset       0.00000     3.00000  0.00000
      Dial
       High      123.00000   123.00000      inf
       Current    12.00000     2.00000  3.00000
       Low      -456.00000  -456.00000     -inf

    """
    if not axes:
        print("need at least one axis name/object")
        return
    max_cols = kwargs.get("max_cols", _MAX_COLS)
    err = kwargs.get("err", _ERR)
    get = functools.partial(safe_get, on_error=ErrorWithTraceback(error_txt=err))

    errors = []
    header = [""]
    User, high_user, user, low_user = ["User"], ["~High"], ["~Current"], ["~Low"]
    Dial, high_dial, dial, low_dial = ["Dial"], ["~High"], ["~Current"], ["~Low"]
    Offset, Spacer = ["Offset"], [""]
    tables = [
        (
            header,
            User,
            high_user,
            user,
            low_user,
            Offset,
            Spacer,
            Dial,
            high_dial,
            dial,
            low_dial,
        )
    ]

    for axis in global_map.get_axis_objects_iter(*axes):
        # get limits in USER units.
        low, high = safe_get(axis, "limits", on_error=(err, err))
        offset = safe_get(axis, "offset", on_error=float("nan"))
        if len(header) == max_cols:
            header = [None]
            User, high_user, user, low_user = (
                ["User"],
                ["~High"],
                ["~Current"],
                ["~Low"],
            )
            Dial, high_dial, dial, low_dial = (
                ["Dial"],
                ["~High"],
                ["~Current"],
                ["~Low"],
            )
            Offset = ["Offset"]
            tables.append(
                (
                    header,
                    User,
                    high_user,
                    user,
                    low_user,
                    Offset,
                    Spacer,
                    Dial,
                    high_dial,
                    dial,
                    low_dial,
                )
            )
        unit = axis.config.get("unit", default=None)
        axis_label = global_map.alias_or_name(axis)
        if unit:
            axis_label += "[{0}]".format(unit)
        header.append(axis_label)
        User.append(None)
        high_user.append(high if high is not None else _MISSING_VAL)
        position = get(axis, "position")
        user.append(position)
        low_user.append(low if low is not None else _MISSING_VAL)
        Dial.append(None)
        high_dial.append(axis.user2dial(high) if high is not None else _MISSING_VAL)
        dial_position = get(axis, "dial")
        dial.append(dial_position)
        low_dial.append(axis.user2dial(low) if low is not None else _MISSING_VAL)
        Offset.append(offset)

        if err in [str(position), str(dial_position)]:
            errors.append((axis_label, dial_position))

    for table in tables:
        print("")
        print(_tabulate(table).replace("~", " "))

    _print_errors_with_traceback(errors, device_type="motor")


def stm(*axes, read_hw=False):
    """
    Displays state information of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    table = [("Axis", "Status")]
    table += [
        (
            global_map.alias_or_name(axis),
            safe_get(
                axis,
                "state",
                on_error=ErrorWithTraceback(error_txt=_ERR),
                read_hw=read_hw,
            ),
        )
        for axis in global_map.get_axis_objects_iter(*axes)
    ]
    print(_tabulate(table))

    errors = []
    for label, state in table:
        if str(state) == _ERR:
            errors.append((label, state))

    _print_errors_with_traceback(errors, device_type="motor")


def sta(read_hw=False):
    """
    Displays state information about all axes

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    return stm(*list(global_map.get_axes_iter()), read_hw=read_hw)


def mv(*args):
    """
    Moves given axes to given absolute positions

    Arguments are interleaved axis and respective absolute target position.
    Example::

        >>> mv(th, 180, chi, 90)

    See Also: move
    """
    move(*args)


def umv(*args):
    """
    Moves given axes to given absolute positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective absolute target position.
    """
    __umove(*args)


def mvr(*args):
    """
    Moves given axes to given relative positions

    Arguments are interleaved axis and respective relative target position.
    Example::

        >>> mv(th, 180, chi, 90)
    """
    __move(*args, relative=True)


def umvr(*args):
    """
    Moves given axes to given relative positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective relative target position.
    """
    __umove(*args, relative=True)


def move(*args, **kwargs):
    """
    Moves given axes to given absolute positions

    Arguments are interleaved axis and respective absolute target position.
    Example::

        >>> mv(th, 180, chi, 90)

    See Also: mv
    """
    __move(*args, **kwargs)


def __row_positions(positions, motors, fmt, sep=" "):
    positions = [positions[m] for m in motors]
    return __row(positions, fmt, sep="  ")


def __row(cols, fmt, sep=" "):
    return sep.join([format(col, fmt) for col in cols])


def __umove(*args, **kwargs):
    kwargs["wait"] = False
    group, motor_pos = __move(*args, **kwargs)
    with error_cleanup(group.stop):
        motor_names = [global_map.alias_or_name(axis) for axis in motor_pos]
        col_len = max(max(map(len, motor_names)), 8)
        hfmt = "^{width}".format(width=col_len)
        rfmt = ">{width}.03f".format(width=col_len)
        print("")
        print(__row(motor_names, hfmt, sep="  "))

        while group.is_moving:
            positions = group.position
            row = __row_positions(positions, motor_pos, rfmt, sep="  ")
            print("\r" + row, end="", flush=True)
            sleep(0.1)
        # print last time for final positions
        positions = group.position
        row = __row_positions(positions, motor_pos, rfmt, sep="  ")
        print("\r" + row, end="", flush=True)
        print("")

    return group, motor_pos


def __move(*args, **kwargs):
    wait, relative = kwargs.get("wait", True), kwargs.get("relative", False)
    motor_pos = dict()
    for m, p in zip(global_map.get_axis_objects_iter(*args[::2]), args[1::2]):
        motor_pos[m] = p
    group = Group(*motor_pos.keys())
    group.move(motor_pos, wait=wait, relative=relative)

    return group, motor_pos


def plotselect(*counters):
    """
    Selects counters to plot and used by alignment functions (cen, peak, etc).
    User-level function built on top of bliss.common.scans.plotselect()
    """

    # If called without arguments, prints help.
    if not counters:
        print("")
        print("plotselect usage:")
        print("    plotselect(<counters>*)")
        print("example:")
        print("    plotselect(counter1, counter2)")
        print("")
    else:
        scans.plotselect(*counters)
    print("")
    print("Currently plotted counter(s):")
    for cnt_name in scans.get_plotted_counters():
        print(f"- {cnt_name}")
    print("")


def prdef(obj_or_name):
    """
    Shows the text of the source code for an object or the name of an object.
    """
    is_arg_str = isinstance(obj_or_name, str)
    if is_arg_str:
        obj, name = getattr(setup_globals, obj_or_name), obj_or_name
    else:
        obj = obj_or_name
        name = None
    try:
        real_name = obj.__name__
    except AttributeError:
        real_name = str(obj)
    if name is None:
        name = real_name

    if (
        inspect.ismodule(obj)
        or inspect.isclass(obj)
        or inspect.istraceback(obj)
        or inspect.isframe(obj)
        or inspect.iscode(obj)
    ):
        pass
    elif inspect.ismethod(obj) or inspect.isfunction(obj):
        obj = inspect.unwrap(obj)
    else:
        try:
            obj = type(obj)
        except:
            pass

    fname = inspect.getfile(obj)
    # make sure cache reloads changed file on disk
    linecache.checkcache(fname)
    lines, line_nb = inspect.getsourcelines(obj)

    if name == real_name or is_arg_str:
        header = "'{0}' is defined in:\n{1}:{2}\n".format(name, fname, line_nb)
    else:
        header = "'{0}' is an alias for '{1}' which is defined in:\n{2}:{3}\n".format(
            name, real_name, fname, line_nb
        )
    print(header)
    print(__pyhighlight("".join(lines)))


def cntdict():
    """
    Return a dict of counters
    """

    counters_dict = dict()
    shape = ["0D", "1D", "2D"]

    for cnt in global_map.get_counters_iter():
        prefix, _, short_name = cnt.fullname.rpartition(":")
        counters_dict[cnt.fullname] = (
            shape[len(cnt.shape)],
            cnt.controller.name if cnt.controller else prefix,
            short_name,
            global_map.aliases.get_alias(cnt),
        )
    return counters_dict


def lscnt():
    """
    Display the list of all counters, sorted alphabetically
    """
    table_info = []
    for counter_name, counter_info in sorted(cntdict().items()):
        table_info.append(itertools.chain([counter_name], counter_info))
    print("")
    print(
        str(
            tabulate(
                table_info, headers=["Fullname", "Shape", "Controller", "Name", "Alias"]
            )
        )
    )


def edit_roi_counters(detector, acq_time=None):
    """
    Edit the given detector ROI counters.
    When called without arguments, it will use the image from specified detector
    from the last scan/ct as a reference. If 'acq_time' is specified,
    it will do a 'ct()' with the given count time to acquire a new image.

        BLISS [1]: ct(0.1, pilatus1)
        BLISS [2]: edit_roi_counters(pilatus1)
    """
    roi_counters = detector.roi_counters
    name = f"{detector.name} [{roi_counters.config_name}]"

    if acq_time:
        setup_globals.SCAN_DISPLAY.auto = True
        scan = ct(acq_time, detector)
    else:
        try:
            scan = SCANS[-1]
        except IndexError:
            print(
                f"SCANS list is empty -- do an acquisition with {detector.name} before editing roi counters"
            )
            return
        else:
            for node in scan.nodes:
                try:
                    # just make sure there is at least an image from this detector;
                    # only acq. channels have .fullname, the easiest is to try...except
                    # for the test
                    if node.fullname == f"{detector.name}:image":
                        break
                except AttributeError:
                    continue
            else:
                print(
                    f"Last scan did not save an image from {detector.name}: do an acquisition before editing roi counters"
                )
                return

    plot = scan.get_plot(detector.image, wait=True)
    if not plot:
        print("Flint is not available -- cannot edit roi counters")
        return

    selections = []
    for roi_name, roi in roi_counters.items():
        selection = dict(
            kind="Rectangle",
            origin=(roi.x, roi.y),
            size=(roi.width, roi.height),
            label=roi_name,
        )
        selections.append(selection)
    print(("Waiting for ROI edition to finish on {}...".format(name)))
    selections = plot.select_shapes(selections)
    roi_labels, rois = [], []
    ignored = 0
    for selection in selections:
        label = selection["label"]
        if not label:
            ignored += 1
            continue
        x, y = map(int, map(round, selection["origin"]))
        w, h = map(int, map(round, selection["size"]))
        rois.append((x, y, w, h))
        roi_labels.append(label)
    if ignored:
        print(("{} ROI(s) ignored (no name)".format(ignored)))
    roi_counters.clear()
    roi_counters[roi_labels] = rois
    print(("Applied ROIS {} to {}".format(", ".join(sorted(roi_labels)), name)))


def info(obj):
    """
    In Bliss `__info__` is used by the command line interface (Bliss shell or Bliss repl) 
    to enquire information of the internal state of any object / controller in case it is 
    available. this info function is to be seen as equivalent of str(obj) or repr(obj) in
    this context.
    
    if *obj* has `__info__` implemented this `__info__` function will be called. As a fallback 
    option (`__info__` not implemented) repr(obj) is used. 
    """
    try:
        tmp = obj.__info__()
        assert type(tmp) is str
        return tmp
    except:
        return repr(obj)


@contextlib.contextmanager
def bench():
    """
    Basic timing of procedure, this has to be use like this:
    with bench():
         wa()
         ascan(roby,0,1,10,0.1,diode)
    """
    start_time = time.time()
    yield
    duration = time.time() - start_time

    print(f"Execution time: {timedisplay.duration_format(duration)}")
