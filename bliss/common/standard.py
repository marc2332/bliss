# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Standard bliss macros (:func:`~bliss.common.standard.wa`, \
:func:`~bliss.common.standard.mv`, etc)
"""
from bliss.common import scans
from bliss.common.scans import *
from bliss.common.plot import plot
from bliss.common.axis import SoftAxis
from bliss.common.measurement import SoftCounter
from bliss.common.cleanup import cleanup, error_cleanup

__all__ = (
    [
        "wa",
        "wm",
        "sta",
        "mv",
        "umv",
        "mvr",
        "umvr",
        "move",
        "prdef",
        "set_log_level",
        "sync",
    ]
    + scans.__all__
    + ["cleanup", "error_cleanup", "plot", "lscnt"]
    + ["SoftAxis", "SoftCounter", "edit_roi_counters"]
)

import collections
import itertools
import inspect
import logging
import functools
import linecache
import gevent

from six import print_
from gevent import sleep
from tabulate import tabulate

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

from bliss import setup_globals
from bliss.common.motor_group import Group
from bliss.common.utils import (
    OrderedDict,
    get_objects_iter,
    get_objects_type_iter,
    get_axes_iter,
    get_axes_positions_iter,
    safe_get,
)
from bliss.common.measurement import BaseCounter
from bliss.shell.cli import repl

_ERR = "!ERR"
_MAX_COLS = 9
_MISSING_VAL = "-----"
_FLOAT_FORMAT = ".05f"


_log = logging.getLogger("bliss.standard")


def _tabulate(data, **kwargs):
    kwargs.setdefault("headers", "firstrow")
    kwargs.setdefault("floatfmt", _FLOAT_FORMAT)
    kwargs.setdefault("numalign", "right")

    return str(tabulate(data, **kwargs))


def __pyhighlight(code, bg="dark", outfile=None):
    formatter = TerminalFormatter(bg=bg)
    return highlight(code, PythonLexer(), formatter, outfile=outfile)


def sync(*axes):
    """
    Forces axes synchronization with the hardware

    Args:
        axes: list of axis objects or names. If no axis is given, it syncs all
              all axes present in the session
    """
    if axes:
        axes = get_objects_iter(*axes)
    else:
        axes = get_axes_iter()
    for axis in axes:
        axis.sync_hard()


def wa(**kwargs):
    """
    Displays all positions (Where All) in both user and dial units
    """
    max_cols = kwargs.get("max_cols", _MAX_COLS)
    err = kwargs.get("err", _ERR)
    get = functools.partial(safe_get, on_error=err)

    print_("Current Positions (user, dial)")
    header, pos, dial = [], [], []
    tables = [(header, pos, dial)]
    for axis_name, position, dial_position, axis_unit in get_axes_positions_iter(
        on_error=_ERR
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

    for table in tables:
        print_()
        print_(_tabulate(table))


def wm(*axes, **kwargs):
    """
    Displays information (position - user and dial, limits) of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis
    """
    if not axes:
        print_("need at least one axis name/object")
        return
    max_cols = kwargs.get("max_cols", _MAX_COLS)
    err = kwargs.get("err", _ERR)
    get = functools.partial(safe_get, on_error=err)

    header = [""]
    User, high_user, user, low_user = ["User"], [" High"], [" Current"], [" Low"]
    Dial, high_dial, dial, low_dial = ["Dial"], [" High"], [" Current"], [" Low"]
    tables = [
        (header, User, high_user, user, low_user, Dial, high_dial, dial, low_dial)
    ]
    for axis in get_objects_iter(*axes):
        low, high = safe_get(axis, "limits", on_error=(err, err))
        if len(header) == max_cols:
            header = [None]
            User, high_user, user, low_user = (
                ["User"],
                [" High"],
                [" Current"],
                [" Low"],
            )
            Dial, high_dial, dial, low_dial = (
                ["Dial"],
                [" High"],
                [" Current"],
                [" Low"],
            )
            tables.append(
                (
                    header,
                    User,
                    high_user,
                    user,
                    low_user,
                    Dial,
                    high_dial,
                    dial,
                    low_dial,
                )
            )
        unit = axis.config.get("unit", default=None)
        axis_label = axis.name
        if unit:
            axis_label += "[{0}]".format(unit)
        header.append(axis_label)
        User.append(None)
        high_user.append(high if high != None else _MISSING_VAL)
        user.append(get(axis, "position"))
        low_user.append(low if low != None else _MISSING_VAL)
        Dial.append(None)
        high_dial.append(axis.user2dial(high) if high != None else _MISSING_VAL)
        dial.append(get(axis, "dial"))
        low_dial.append(axis.user2dial(low) if low != None else _MISSING_VAL)

    for table in tables:
        print_()
        print_(_tabulate(table))


def stm(*axes):
    """Displays axis state (not implemented yet!)"""
    raise NotImplementedError


def sta(read_hw=False):
    """
    Displays state information about all axes

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    global __axes
    table = [("Axis", "Status")]
    table += [
        (
            axis.name,
            safe_get(axis, "state", on_error="<status not available>", read_hw=read_hw),
        )
        for axis in get_axes_iter()
    ]
    print_(_tabulate(table))


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
        motor_names = [axis.name for axis in motor_pos]
        col_len = max(max(map(len, motor_names)), 8)
        hfmt = "^{width}".format(width=col_len)
        rfmt = ">{width}.03f".format(width=col_len)
        print_()
        print_(__row(motor_names, hfmt, sep="  "))

        while group.is_moving:
            positions = group.position()
            row = __row_positions(positions, motor_pos, rfmt, sep="  ")
            print_("\r" + row, end="", flush=True)
            sleep(0.1)
        # print last time for final positions
        positions = group.position()
        row = __row_positions(positions, motor_pos, rfmt, sep="  ")
        print_("\r" + row, end="", flush=True)
        print_()

    return group, motor_pos


def __move(*args, **kwargs):
    wait, relative = kwargs.get("wait", True), kwargs.get("relative", False)
    motor_pos = OrderedDict()
    for m, p in zip(get_objects_iter(*args[::2]), args[1::2]):
        motor_pos[m] = p
    group = Group(*motor_pos.keys())
    group.move(motor_pos, wait=wait, relative=relative)

    return group, motor_pos


def prdef(obj_or_name):
    """
    Shows the text of the source code for an object or the name of an object.
    """
    is_arg_str = isinstance(obj_or_name, (str, unicode))
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
        or inspect.ismethod(obj)
        or inspect.isfunction(obj)
        or inspect.istraceback(obj)
        or inspect.isframe(obj)
        or inspect.iscode(obj)
    ):
        pass
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
    print_(header)
    print_(__pyhighlight("".join(lines)))


def _check_log_level(level):
    if isinstance(level, (int, long)):
        rv = level
    else:
        rv = getattr(logging, level.upper())
    return rv


def set_log_level(level=logging.root.level):
    """
    Adjusts the log level
    
    Without arguments, resets the level back to the one setup at
    beginning of the session.

    Args:
        level (int or str): new log level can be constant (ex: logging.INFO) or
                            case insensitive equivalent string (ex: 'Info')
    """
    logging.root.setLevel(_check_log_level(level))


def cntdict():
    """
    Return a dict of counters
    """
    counters_dict = dict()
    shape = ["0D", "1D", "2D"]

    if repl.REPL is None:
        env_dict = dict()
    else:
        env_dict = repl.REPL.get_globals()

    for name, obj in itertools.chain(
        inspect.getmembers(setup_globals),
        env_dict.iteritems() if env_dict is not None else {},
    ):
        if isinstance(obj, BaseCounter):
            counters_dict[obj.fullname] = (
                shape[len(obj.shape)],
                obj.controller.name if obj.controller else "None",
            )
        elif hasattr(obj, "counters") and isinstance(
            obj.counters, collections.Iterable
        ):
            for cnt in obj.counters:
                if isinstance(cnt, BaseCounter):
                    tmp = cnt.fullname.split(".")
                    controller_name = ".".join(tmp[:-1])
                    counters_dict[cnt.fullname] = (
                        shape[len(cnt.shape)],
                        controller_name,
                    )
    return counters_dict


def lscnt():
    """
    Display the list of all counters, sorted alphabetically
    """
    table_info = []
    for counter_name, counter_info in sorted(cntdict().iteritems()):
        table_info.append(itertools.chain([counter_name], counter_info))
    print_()
    print_(str(tabulate(table_info, headers=["Name", "Shape", "Controller"])))


def edit_roi_counters(detector, acq_time=None):
    """
    Edit the given detector ROI counters.
    When called without arguments, it will use the last point of the last
    scan/ct as a reference. If 'ct' is specified, it will do a 'ct()' with
    the given count time.

        BLISS [1]: ct(0.1, pilatus1)
        BLISS [2]: edit_roi_counters(pilatus1)
    """
    roi_counters = detector.roi_counters
    name = "{} [{}]".format(detector.name, roi_counters.config_name)

    if acq_time:
        setup_globals.SCAN_DISPLAY.auto = True
        scan = ct(acq_time, detector, return_scan=True)
    else:
        scan = setup_globals.SCANS[-1]

    plot = scan.get_plot(detector.image, wait=True)

    selections = []
    for roi_name, roi in roi_counters.items():
        selection = dict(
            kind="Rectangle",
            origin=(roi.x, roi.y),
            size=(roi.width, roi.height),
            label=roi_name,
        )
        selections.append(selection)
    print("Waiting for ROI edition to finish on {}...".format(name))
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
        print("{} ROI(s) ignored (no name)".format(ignored))
    roi_counters.clear()
    roi_counters[roi_labels] = rois
    print("Applied ROIS {} to {}".format(", ".join(sorted(roi_labels)), name))
