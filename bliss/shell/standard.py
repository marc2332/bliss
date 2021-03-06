# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Standard functions provided to the BLISS shell.
"""

import contextlib
import inspect
import itertools
import linecache
import logging
import numpy
import os
import shutil
import socket
import subprocess
import sys
import time
import typeguard
import typing

from pprint import pprint  # noqa (pprint is exported in shell from this module)
from gevent import sleep, Timeout

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

from prompt_toolkit import print_formatted_text, HTML

import bliss
from bliss import global_map, global_log, setup_globals, current_session
from bliss.common import timedisplay
from bliss.common.plot import plot  # noqa
from bliss.common.standard import (  # noqa
    iter_counters,
    iter_axes_state,
    iter_axes_state_all,
    iter_axes_position,
    iter_axes_position_all,
    sync,
    info,
    __move,
    reset_equipment,
)
from bliss.common.standard import wid as std_wid
from bliss.common.event import connect
from bliss.controllers.lima.limatools import *
from bliss.controllers.lima import limatools
from bliss.controllers.lima import roi as lima_roi
from bliss.common.protocols import CounterContainer
from bliss.common import measurementgroup
from bliss.common.soft_axis import SoftAxis  # noqa
from bliss.common.counter import SoftCounter, Counter  # noqa
from bliss.common.utils import (
    ShellStr,
    typecheck_var_args_pattern,
    modify_annotations,
    custom_error_msg,
    shorten_signature,
    TypeguardTypeError,
)
from bliss.config.conductor.client import get_redis_proxy

from bliss.common.measurementgroup import MeasurementGroup
from bliss.shell.dialog.helpers import find_dialog, dialog as dialog_dec_cls


# objects given to Bliss shell user
from bliss.common.standard import mv, mvr, mvd, mvdr, move, rockit  # noqa
from bliss.common.cleanup import cleanup, error_cleanup  # noqa

from bliss.common import scans
from bliss.common.scans import *
from bliss.scanning.scan import Scan
from bliss.comm.rpc import Client
from bliss.common import logtools
from bliss.common.logtools import elog_print, user_print
from bliss.common.interlocks import interlock_state
from bliss.common.session import get_current_session
from bliss.data import lima_image

from bliss.scanning.scan_tools import (
    cen,
    goto_cen,
    com,
    goto_com,
    peak,
    goto_peak,
    trough,
    goto_min,
    where,
    find_position,
    goto_custom,
    fwhm,  # noqa: F401
)
from bliss.common.plot import meshselect  # noqa: F401
from bliss.common import plot as plot_module
from bliss.shell.cli import user_dialog, pt_widgets

import tabulate

from bliss.common.utils import typeguardTypeError_to_hint, chunk_list
from typing import Optional, Union
from bliss.controllers.lima.lima_base import Lima
from bliss.common.protocols import Scannable
from bliss.common.types import (
    _countable,
    _scannable_or_name,
    _float,
    _providing_channel,
)

from bliss.common.profiling import time_profile

############## imports that are only used simpyly the
############## shell user access to these functions

# hint: don't forget to add to __all__ as well
from numpy import (
    sin,
    cos,
    tan,
    arcsin,
    arccos,
    arctan,
    arctan2,
    log,
    log10,
    sqrt,
    exp,
    power,
    deg2rad,
    rad2deg,
)
from numpy.random import rand
from time import asctime as date

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
        "mvd",
        "umvd",
        "mvdr",
        "umvdr",
        "rockit",
        "move",
        "lsmot",
        "lsconfig",
        "plotinit",
        "plotselect",
        "flint",
        "prdef",
        "sync",
        "lslog",
        "lsdebug",
        "debugon",
        "debugoff",
        "interlock_show",
        "interlock_state",
        "info",
        "bench",
        "clear",
        "newproposal",
        "endproposal",
        "newsample",
        "newcollection",
        "newdataset",
        "enddataset",
        "silx_view",
        "pymca",
        "cen",
        "goto_cen",
        "peak",
        "goto_peak",
        "trough",
        "goto_min",
        "com",
        "goto_com",
        "where",
        "fwhm",
        "menu",
        "pprint",
        "find_position",
        "goto_custom",
        "time_profile",
        "tw",
    ]
    + scans.__all__
    + ["lprint", "ladd", "elog_print", "elog_add"]
    + [
        "cleanup",
        "error_cleanup",
        "plot",
        "lscnt",
        "lsmg",
        "lsobj",
        "wid",
        "reset_equipment",
    ]
    + ["SoftAxis", "SoftCounter", "edit_roi_counters", "edit_mg"]
    + list(limatools.__all__)
    + [
        "sin",
        "cos",
        "tan",
        "arcsin",
        "arccos",
        "arctan",
        "arctan2",
        "log",
        "log10",
        "sqrt",
        "exp",
        "power",
        "deg2rad",
        "rad2deg",
        "rand",
        "sleep",
        "date",
    ]
)

tabulate.PRESERVE_WHITESPACE = True

_ERR = "!ERR"
_MAX_COLS = 9
_MISSING_VAL = "-----"
_FLOAT_FORMAT = ".05f"


def _print_errors_with_traceback(errors, device_type="motor"):
    """
    RE-raise caught errors with original traceback
    """
    for (label, error_with_traceback_obj) in errors:
        exc_type, exc_val, exc_tb = error_with_traceback_obj.exc_info
        try:
            # we re-raise in order to pass the motor label to the error msg
            # else calling sys.excepthook(*sys.exc_info()) would be fine
            raise exc_type(
                f"Error on {device_type} '{label}': {str(exc_val)}"
            ).with_traceback(exc_tb)
        except Exception:
            sys.excepthook(*sys.exc_info())


def _tabulate(data, **kwargs):
    kwargs.setdefault("headers", "firstrow")
    kwargs.setdefault("floatfmt", _FLOAT_FORMAT)
    kwargs.setdefault("numalign", "right")

    return str(tabulate.tabulate(data, **kwargs))


def __row_positions(positions, motors, fmt, sep=" "):
    positions = [positions[m] for m in motors]
    return __row(positions, fmt, sep="  ")


def __row(cols, fmt, sep=" "):
    return sep.join([format(col, fmt) for col in cols])


def lslog(glob: str = None, debug_only: bool = False):
    """
    Search for loggers.

    It uses a pattern matching normally used by shells.
    Common operators are `*` for any number of characters
    and `?` for one character of any type.

    Args:
        glob: a logger name with optional glob matching
        debug_only: True to display only loggers at debug level
                    (equivalent to lslog)

    Examples:

    >>> lslog()  # prints all loggers

    >>> lslog('*motor?')  # prints loggers that finish with 'motor' + 1 char
                          # like motor1, motor2, motork

    >>> lslog('*Socket*')  # prints loggers that contains 'Socket'

    """
    if glob is None:
        loggers = {
            **global_log._find_loggers("bliss*"),
            **global_log._find_loggers("flint*"),
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
        level = logging.getLevelName(logger.getEffectiveLevel())
        if logger.disabled:
            level = "%s [DISABLED]" % level
        print(msgfmt.format(name, level, width=maxlen))
    if output:
        print("")
    else:
        print("No loggers found.\n")


def lsdebug(glob: str = None, debug_only=False) -> None:
    """
    Display current Loggers at DEBUG level
    """
    lslog(glob, debug_only=True)


def debugon(glob_logger_pattern_or_obj) -> None:
    """
    Activate debug-level logging for a specifig logger or an object

    Args:
        glob_logger_pattern_or_obj: glob style pattern matching for logger name, or instance

    Hints on glob: pattern matching normally used by shells
                   common operators are * for any number of characters
                   and ? for one character of any type

    Return:
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


@typeguard.typechecked
def lscnt(counter_container: typing.Union[CounterContainer, Counter, None] = None):
    """
    Display the list of all counters, sorted alphabetically
    """
    if counter_container is None:
        counters = None
    elif isinstance(counter_container, CounterContainer):
        counters = counter_container.counters
    else:
        # must be Counter
        counters = [counter_container]

    table_info = []
    for counter_name, shape, prefix, name, alias in sorted(iter_counters(counters)):
        if alias:
            alias = "      *"
        table_info.append(itertools.chain([counter_name], (shape, prefix, alias, name)))
    print("")
    print(
        str(
            tabulate.tabulate(
                table_info, headers=["Fullname", "Shape", "Controller", "Alias", "Name"]
            )
        )
    )


def _lsmg():
    """
    Return the list of measurment groups
    Indicate the current active one with a star char: '*'
    """
    active_mg_name = measurementgroup.get_active_name()
    lsmg_str = ""

    for mg_name in measurementgroup.get_all_names():
        if mg_name == active_mg_name:
            lsmg_str += f" * {mg_name}\n"
        else:
            lsmg_str += f"   {mg_name}\n"

    return lsmg_str


def lsmg():
    """
    Print the list of measurment groups
    Indicate the current active one with a star char: '*'
    """
    print(_lsmg())


def lsobj(pattern=None):
    """
    Print the list of BLISS object in current session matching the
    <pattern> string.
    <pattern> can contain jocker characters like '*' or '?'.
    NB: print also badly initilized objects...
    """

    for obj_name in bliss.common.standard._lsobj(pattern):
        print(obj_name, end="  ")

    print("")


def wid():
    """
    Print the list of undulators defined in the session
    and their positions.
    Print all axes of the ID device server.
    """
    print(std_wid())


@typeguard.typechecked
def stm(*axes: _scannable_or_name, read_hw: bool = False):
    """
    Display state information of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    data = iter_axes_state(*axes, read_hw=read_hw)

    table = [(axis, state) for (axis, state) in data]

    print(_tabulate([("Axis", "Status")] + table))

    errors = []
    for label, state in table:
        if str(state) == _ERR:
            errors.append((label, state))

    _print_errors_with_traceback(errors, device_type="motor")


@typeguard.typechecked
def sta(read_hw: bool = False):
    """
    Return state information about all axes

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    return stm(*list(global_map.get_axes_iter()), read_hw=read_hw)


_ERR = "!ERR"
_MAX_COLS = 9
_MISSING_VAL = "-----"


def tw(*motors):
    """
    Display an user interface to move selected motors. (Limited to 5 motors)

    Args:
        motors (~bliss.common.axis.Axis): motor axis

    example:
      DEMO [18]: tw(m0, m1, m2)
    """
    import gevent

    def get_url(timeout=None):
        key = "tweak_ui_" + current_session.name
        redis = get_redis_proxy()

        if timeout is None:
            value = redis.lpop(key)
        else:
            result = redis.blpop(key, timeout=timeout)
            if result is not None:
                key, value = result
                redis.lpush(key, value)
            else:
                value = None

        if value is None:
            raise ValueError(
                f"Tweak UI: cannot retrieve Tweak RPC server address from pid "
            )
        url = value.decode().split()[-1]
        return url

    def wait_tweak(tweak):
        while True:
            try:
                tweak.loaded
                break
            except socket.error as e:
                pass
            gevent.sleep(0.3)

    def create_env():
        from bliss.config.conductor.client import get_default_connection

        beacon = get_default_connection()
        beacon_config = f"{beacon._host}:{beacon._port}"

        env = dict(os.environ)
        env["BEACON_HOST"] = beacon_config
        return env

    if len(motors) > 5:
        raise TypeError("This tool can only display a maximum of 5 motors")

    try:
        task = None
        with Timeout(10):
            try:
                url = get_url()
            except ValueError:
                pass
            else:
                tweak = Client(url)
                try:
                    tweak.close_new = True
                except socket.error:
                    pass

            tweak = None
            args = f"{sys.executable} -m bliss.shell.qtapp.tweak_ui --session {current_session.name} --motors".split()
            for motor in motors:
                args.append(motor.name)

            process = subprocess.Popen(args, env=create_env())

            try:
                url = get_url(timeout=10)
                tweak = Client(url)
                wait_tweak(tweak)
                connect(tweak, "ct_requested", _tw_ct_requested)
                print("Tweak UI started")
            except Exception:
                process.kill()
                print("Tweak UI launch has failed, please try again")

    except Timeout:
        process.kill()
        raise TimeoutError("The application took too long to start")


def _tw_ct_requested(acq_time, sender):
    ct(acq_time, title="auto_ct")


def wa(**kwargs):
    """
    Display all positions (Where All) in both user and dial units
    """
    print("Current Positions: user")
    print("                   dial")

    max_cols = kwargs.get("max_cols", _MAX_COLS)

    header, pos, dial = [], [], []
    tables = [(header, pos, dial)]
    errors = []

    data = iter_axes_position_all(**kwargs)
    for axis_name, axis_unit, position, dial_position in data:
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

        _print_errors_with_traceback(errors, device_type="motor")

    for table in tables:
        print("")
        print(_tabulate(table))


def lsmot():
    """
    Display names of motors configured in current session.
    """

    motor_list = bliss.common.standard._lsmot()

    # Maximal length of objects names (min 5).
    display_width = shutil.get_terminal_size().columns
    if len(motor_list) == 0:
        max_length = 5
        print("No motor found in current session's config.")
    else:
        max_length = max([len(x) for x in motor_list])

        # Number of items displayable on one line.
        item_number = int(display_width / max_length) + 1

        motor_list.sort(key=str.casefold)

        user_print("Motors configured in current session:")
        user_print("-------------------------------------")
        print(tabulate.tabulate(chunk_list(motor_list, item_number), tablefmt="plain"))
        user_print("\n")


from bliss.config import static


def lsconfig():
    """
    Print all objects found in config.
    Not only objects declared in current session's config.
    """
    obj_dict = dict()

    config = static.get_config()

    # Maximal length of objects names (min 5).
    display_width = shutil.get_terminal_size().columns

    print()

    for name in config.names_list:
        c = config.get_config(name).get("class")
        # print(f"{name}: {c}")
        if c is None and config.get_config(name).plugin == "emotion":
            c = "Motor"
        try:
            obj_dict[c].append(name)
        except KeyError:
            obj_dict[c] = list()
            obj_dict[c].append(name)

    # For each class
    for cc in obj_dict.keys():
        user_print(f"{cc}: ")
        if cc is None:
            user_print("----")
        else:
            user_print("-" * len(cc))
        obj_list = list()

        # put all objects of this class in a list
        while obj_dict[cc]:
            obj_list.append(obj_dict[cc].pop())
        # print(obj_list)

        max_length = max([len(x) for x in obj_list])

        # Number of items displayable on one line.
        item_count = int(display_width / max_length) + 1

        print(tabulate.tabulate(chunk_list(obj_list, item_count), tablefmt="plain"))
        user_print()


@custom_error_msg(
    TypeguardTypeError,
    "intended usage: wm(axis1, axis2, ... ) Hint:",
    new_exception_type=RuntimeError,
    display_original_msg=True,
)
@shorten_signature(annotations={"axes": "axis1, axis2, ... "}, hidden_kwargs=("kwargs"))
@typeguard.typechecked
def wm(*axes: _scannable_or_name, **kwargs):
    """
    Display information (position - user and dial, limits) of the given axes

    Args:
        axis: A motor axis

    Example:

    >>> wm(m2, m1, m3)

    .. code-block::

                            m2      m1[mm]       m3
          --------  ----------  ----------  -------
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
        print(
            "wm() needs at least one axis name/object as parameter.\n"
            "example: wm(mot1)\n"
            "         wm(mot1, mot2, ... motN)"
        )
        return

    max_cols = kwargs.get("max_cols", _MAX_COLS)
    err = kwargs.get("err", _ERR)

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

    for axis in iter_axes_position(*axes, **kwargs):

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
        axis_label = axis.axis_name
        if axis.unit:
            axis_label += "[{0}]".format(axis.unit)
        header.append(axis_label)
        User.append(None)
        user_high_limit, dial_high_limit = (
            (axis.user_high_limit, axis.dial_high_limit)
            if axis.user_high_limit not in (None, err)
            else (_MISSING_VAL, _MISSING_VAL)
        )
        user_low_limit, dial_low_limit = (
            (axis.user_low_limit, axis.dial_low_limit)
            if axis.user_low_limit not in (None, err)
            else (_MISSING_VAL, _MISSING_VAL)
        )
        high_user.append(user_high_limit)
        position = axis.user_position
        user.append(position)
        low_user.append(user_low_limit)
        Dial.append(None)
        high_dial.append(dial_high_limit)
        dial_position = axis.dial_position
        dial.append(dial_position)
        low_dial.append(dial_low_limit)
        Offset.append(axis.offset)

        if err in [str(position), str(dial_position)]:
            errors.append((axis_label, dial_position))

    _print_errors_with_traceback(errors, device_type="motor")

    for table in tables:
        print("")
        print(_tabulate(table).replace("~", " "))


@custom_error_msg(
    TypeguardTypeError,
    "intended usage: umv(motor1, target_position_1, motor2, target_position_2, ... )",
    new_exception_type=RuntimeError,
    display_original_msg=False,
)
@modify_annotations({"args": "motor1, pos1, motor2, pos2, ..."})
@typecheck_var_args_pattern([Scannable, _float])
def umv(*args):
    """
    Move given axes to given absolute positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective absolute target position.
    """
    __umove(*args)


@custom_error_msg(
    TypeguardTypeError,
    "intended usage: umvr(motor1, relative_displacement_1, motor2, relative_displacement_2, ... )",
    new_exception_type=RuntimeError,
    display_original_msg=False,
)
@modify_annotations({"args": "motor1, rel. pos1, motor2, rel. pos2, ..."})
@typecheck_var_args_pattern([Scannable, _float])
def umvr(*args):
    """
    Move given axes to given relative positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective relative target position.
    """
    __umove(*args, relative=True)


@custom_error_msg(
    TypeguardTypeError,
    "intended usage: umvd(motor1, target_position_1, motor2, target_position_2, ... )",
    new_exception_type=RuntimeError,
    display_original_msg=False,
)
@modify_annotations({"args": "motor1, pos1, motor2, pos2, ..."})
@typecheck_var_args_pattern([Scannable, _float])
def umvd(*args):
    """
    Move given axes to given absolute dial positions providing updated display of
    the motor(s) user position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective absolute target position.
    """
    __umove(*args, dial=True)


@custom_error_msg(
    TypeguardTypeError,
    "intended usage: umvdr(motor1, relative_displacement_1, motor2, relative_displacement_2, ... )",
    new_exception_type=RuntimeError,
    display_original_msg=False,
)
@modify_annotations({"args": "motor1, rel. pos1, motor2, rel. pos2, ..."})
@typecheck_var_args_pattern([Scannable, _float])
def umvdr(*args):
    """
    Move given axes to given relative dial positions providing updated display of
    the motor(s) user position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective relative target position.
    """
    __umove(*args, relative=True, dial=True)


def __umove(*args, **kwargs):
    kwargs["wait"] = False
    group, motor_pos = __move(*args, **kwargs)
    motors = list(group.axes_with_reals.values())
    with error_cleanup(group.stop):
        motor_names = list()
        for axis in motors:
            if axis.unit:
                motor_names.append(
                    "{}[{}]".format(global_map.alias_or_name(axis), axis.unit)
                )
            else:
                motor_names.append(global_map.alias_or_name(axis))
        col_len = max(max(map(len, motor_names)), 8)
        hfmt = "^{width}".format(width=col_len)
        rfmt = ">{width}.03f".format(width=col_len)
        print("")
        # print("   " + __row(motor_names, hfmt, sep="  "))
        first_row = __row(motor_names, hfmt, sep="  ")
        row_len = len(first_row)
        print(first_row.rjust(row_len + 5))
        print("")
        magic_char = "\033[F"  # "back to previous line" character

        def format_group(group):
            positions = group.position_with_reals
            dials = group.dial_with_reals
            user_pos = __row_positions(positions, motors, rfmt, sep="  ")
            dial_pos = __row_positions(dials, motors, rfmt, sep="  ")
            row = f"user {user_pos}\ndial {dial_pos}"
            ret_depth = magic_char * row.count("\n")
            return f"{ret_depth}{row}"

        previous_line = None
        while group.is_moving:
            previous_line = format_group(group)
            print(previous_line, end="", flush=True)
            sleep(0.1)

        # print last time for final positions
        last_line = format_group(group)
        if previous_line != last_line:
            print(last_line, end="", flush=True)
        print("")

    return group, motor_pos


def __pyhighlight(code, bg="dark", outfile=None):
    formatter = TerminalFormatter(bg=bg)
    return highlight(code, PythonLexer(), formatter, outfile=outfile)


def prdef(obj_or_name):
    """
    Show the text of the source code for an object or the name of an object.
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
        except Exception:
            pass

    fname = inspect.getfile(obj)
    # make sure cache reloads changed file on disk
    linecache.checkcache(fname)
    if obj in current_session._script_source_cache:
        lines, line_nb = current_session._script_source_cache[obj]
    else:
        lines, line_nb = inspect.getsourcelines(obj)

    if name == real_name or is_arg_str:
        header = "'{0}' is defined in:\n{1}:{2}\n".format(name, fname, line_nb)
    else:
        header = "'{0}' is an alias for '{1}' which is defined in:\n{2}:{3}\n".format(
            name, real_name, fname, line_nb
        )
    print(header)
    print(__pyhighlight("".join(lines)))


@typeguard.typechecked
def plotinit(*counters: _providing_channel):
    """
    Select counters to plot and to use only with the next scan command.

    User-level function built on top of bliss.common.scans.plotinit()
    """

    # If called without arguments, prints help.
    if not counters:
        print(
            """
plotinit usage:
    plotinit(<counters>*)                  - Select a set of counters

example:
    plotinit(counter1, counter2)")
    plotinit('*')                          - Select everything
    plotinit('beamviewer:roi_counters:*')  - Select all the ROIs from a beamviewer
    plotinit('beamviewer:*_sum')           - Select any sum ROIs from a beamviewer
"""
        )
    else:
        plot_module.plotinit(*counters)
    print("")

    names = plot_module.get_next_plotted_counters()
    if names:
        print("Plotted counter(s) for the next scan:")
        for cnt_name in names:
            print(f"- {cnt_name}")
    else:
        print("No specific counter(s) for the next scan")
    print("")


@typeguard.typechecked
def plotselect(*counters: _providing_channel):
    """
    Select counters to plot and used by alignment functions (cen, peak, etc).

    User-level function built on top of bliss.common.plot.plotselect()
    """

    # If called without arguments, prints help.
    if not counters:
        print(
            """
plotselect usage:
    plotselect(<counters>*)                  - Select a set of counters

example:
    plotselect(counter1, counter2)")
    plotselect('*')                          - Select everything
    plotselect('beamviewer:roi_counters:*')  - Select all the ROIs from a beamviewer
    plotselect('beamviewer:*_sum')           - Select any sum ROIs from a beamviewer
"""
        )
    else:
        if len(counters) == 1 and counters[0] is None:
            counters = []
        plot_module.plotselect(*counters)
    print("")
    print(
        "Plotted counter(s) last selected with plotselect (could be different from the current display):"
    )
    for cnt_name in plot_module.get_plotted_counters():
        print(f"- {cnt_name}")
    print("")


def flint():
    """
    Return a proxy to the running Flint application used by BLISS, else create
    one.

    If there is problem to create or to connect to Flint, an exception is
    raised.

        # This can be used to start Flint
        BLISS [1]: flint()

        # This can be used to close Flint
        BLISS [1]: f = flint()
        BLISS [2]: f.close()

        # This can be used to kill Flint
        BLISS [1]: f = flint()
        BLISS [2]: f.kill9()
    """
    proxy = plot_module.get_flint(creation_allowed=True, mandatory=True)
    print("Current Flint PID: ", proxy.pid)
    print("")
    return proxy


@typeguardTypeError_to_hint
@typeguard.typechecked
def edit_roi_counters(detector: Lima, acq_time: Optional[float] = None):
    """
    Edit the given detector ROI counters.

    When called without arguments, it will use the image from specified detector
    from the last scan/ct as a reference. If `acq_time` is specified,
    it will do a `ct()` with the given count time to acquire a new image.


    .. code-block:: python

        # Flint will be open if it is not yet the case
        edit_roi_counters(pilatus1, 0.1)

        # Flint must already be open
        ct(0.1, pilatus1)
        edit_roi_counters(pilatus1)
    """
    if acq_time is not None:
        # Open flint before doing the ct
        plot_module.get_flint()
        scans.ct(acq_time, detector.image)

    # Check that Flint is already there
    flint = plot_module.get_flint()
    channel_name = f"{detector.name}:image"

    # That it contains an image displayed for this detector
    try:
        plot_id = flint.get_live_scan_plot(channel_name, "image")
    except:
        # Create a single frame from detector data
        # or a placeholder

        try:
            data = lima_image.image_from_server(detector._proxy, -1)
        except:
            # Else create a checker board place holder
            y, x = numpy.mgrid[0 : detector.image.height, 0 : detector.image.width]
            data = ((y // 16 + x // 16) % 2).astype(numpy.uint8) + 2
            data[0, 0] = 0
            data[-1, -1] = 5

        flint.set_static_image(channel_name, data)
        plot_id = flint.get_live_scan_plot(channel_name, "image")

    # Reach the plot widget
    plot_proxy = plot_module.plot_image(existing_id=plot_id)
    if not plot_proxy:
        raise RuntimeError(
            "Internal error. A plot from this detector was expected but it is not available. Or Flint was closed in between."
        )
    plot_proxy.focus()

    roi_counters = detector.roi_counters
    roi_profiles = detector.roi_profiles

    # Retrieve all the ROIs
    selections = []
    selections.extend(roi_counters.get_rois())
    selections.extend(roi_profiles.get_rois())

    deviceName = (
        f"{detector.name} [{roi_counters.config_name}, {roi_profiles.config_name}]"
    )
    print(f"Waiting for ROI edition to finish on {deviceName}...")
    selections = plot_proxy.select_shapes(
        selections,
        kinds=[
            "lima-rectangle",
            "lima-arc",
            "lima-vertical-profile",
            "lima-horizontal-profile",
        ],
    )

    roi_counters.clear()
    roi_profiles.clear()
    for roi in selections:
        if isinstance(roi, lima_roi.RoiProfile):
            roi_profiles[roi.name] = roi
        else:
            roi_counters[roi.name] = roi

    roi_string = ", ".join(sorted([s.name for s in selections]))
    print(f"Applied ROIS {roi_string} to {deviceName}")


def interlock_show(wago_obj=None):
    """
    Display interlocks configuration on given Wago object (if given)
    or display configuration of all known Wagos
    """
    if wago_obj:
        wago_obj.interlock_show()
    else:
        try:
            wago_instance_list = tuple(
                global_map[id_]["instance"]()
                for id_ in global_map.find_children("wago")
            )
        except TypeError:
            print("No Wago found")
            return
        names = [wago.name for wago in wago_instance_list]
        print_formatted_text(
            HTML(f"Currently configured Wagos: <violet>{' '.join(names)}</violet>\n\n")
        )
        for wago in wago_instance_list:
            wago.interlock_show()


def menu(obj=None, dialog_type: str = None, *args, **kwargs):
    """
    Display a dialog for acting on the object if this is implemented

    Args:
        obj: the object on which you want to operate, if no object is provided
             a complete list of available objects that have implemented some
             dialogs will be displayed.
        dialog_type: the dialog type that you want to display between one
             of the available. If this parameter is omitted and only one dialog
             is available for the given object than that dialog is diplayed,
             if instead more than one dialog is available will be launched a
             first selection dialog to choose from availables and than the
             selected one.

    Examples:

    >>> menu()  # will display all bliss objects that have dialog implemented

    >>> menu(wba)  # will launch the only available dialog for wba: "selection"

    >>> menu(wba, "selection")  # same as previous

    >>> menu(lima_simulator)  # will launch a selection dialog between available
    >>>                       # choices and than the selected one
    """
    if obj is None:
        names = set()
        # remove (_1, _2, ...) ptpython shell items that create false positive
        env = {
            k: v
            for (k, v) in get_current_session().env_dict.items()
            if not k.startswith("_")
        }

        for key, obj in env.items():
            try:
                # intercepts functions like `ascan`
                if obj.__name__ in dialog_dec_cls.DIALOGS.keys():
                    names.add(key)
            except AttributeError:
                try:
                    # intercept class instances like `wago_simulator`
                    if obj.__class__.__name__ in dialog_dec_cls.DIALOGS.keys():
                        names.add(key)

                except AttributeError:
                    pass

        return ShellStr(
            "Dialog available for the following objects:\n\n" + "\n".join(sorted(names))
        )
    dialog = find_dialog(obj)
    if dialog is None:
        return ShellStr("No dialog available for this object")
    try:
        return dialog(dialog_type)
    except ValueError as exc:
        logtools.log_error(dialog, "Error while execution the dialog", exc_info=True)
        return ShellStr(str(exc))


@contextlib.contextmanager
def bench():
    """
    Basic timing of procedure, this has to be use like this:
    with :code:`bench()`:

    >>> wa()
    >>> ascan(roby,0,1,10,0.1,diode)
    """
    start_time = time.time()
    yield
    duration = time.time() - start_time

    print(f"Execution time: {timedisplay.duration_format(duration)}")


def clear():
    """
    Clear terminal screen
    """
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


@typeguard.typechecked
def edit_mg(mg: MeasurementGroup):
    """
    Edit the measurement group with a simple dialog.

    Arguments:
        mg: a measurement group if left to None == default
            measurement group.
    """
    active_mg = measurementgroup.ACTIVE_MG if mg is None else mg
    available_counters = active_mg._available_counters
    try:
        available = list(
            sorted(active_mg._get_available_counters_names(available_counters))
        )
    except AttributeError:
        if mg is None:
            raise RuntimeError("No active measurement group")
        else:
            raise RuntimeError(f"Object **{mg}** is not a measurement group")
    enabled = active_mg._get_enabled_counters_names(available_counters)

    dlgs = [
        user_dialog.UserCheckBox(label=name, defval=name in enabled)
        for name in available
    ]
    nb_counter_per_column = 18
    cnts = [
        user_dialog.Container(dlgs[i : i + nb_counter_per_column], splitting="h")
        for i in range(0, len(dlgs), nb_counter_per_column)
    ]

    dialog = pt_widgets.BlissDialog(
        [cnts],
        title=f"Edition measurement group: **{active_mg.name}**  "
        "enable/disable counters",
    )
    rval = dialog.show()
    if rval:
        selected = set(
            [
                cnt_name
                for cnt_name, enable_flag in zip(available, rval.values())
                if enable_flag
            ]
        )
        available = set(available)
        to_enable = selected - enabled

        disabled = available - enabled
        deselected = available - selected
        to_disable = deselected - disabled

        if to_enable:
            active_mg.enable(*to_enable)
        if to_disable:
            active_mg.disable(*to_disable)


# Data Policy
# from bliss/scanning/scan_saving.py


@typeguard.typechecked
@logtools.elogbook.disable_command_logging
def newproposal(proposal_name: Optional[str] = None):
    """
    Change the proposal name used to determine the saving path.
    """
    current_session.scan_saving.newproposal(proposal_name)


@typeguard.typechecked
@logtools.elogbook.disable_command_logging
def newsample(collection_name: Optional[str] = None, description: Optional[str] = None):
    """
    Same as `newcollection` with sample name equal to the collection name.
    """
    current_session.scan_saving.newsample(collection_name, description=description)


@typeguard.typechecked
@logtools.elogbook.disable_command_logging
def newcollection(
    collection_name: Optional[str] = None,
    sample_name: Optional[str] = None,
    sample_description: Optional[str] = None,
):
    """
    Change the collection name used to determine the saving path.
    Metadata can be modified later if needed.
    """
    current_session.scan_saving.newcollection(
        collection_name, sample_name=sample_name, sample_description=sample_description
    )


@typeguard.typechecked
@logtools.elogbook.disable_command_logging
def newdataset(
    dataset_name: Optional[Union[str, int]] = None,
    description: Optional[str] = None,
    sample_name: Optional[str] = None,
    sample_description: Optional[str] = None,
):
    """
    Change the dataset name used to determine the saving path.

    The description can be modified until the dataset is closed.
    """
    current_session.scan_saving.newdataset(
        dataset_name,
        description=description,
        sample_name=sample_name,
        sample_description=sample_description,
    )


@logtools.elogbook.disable_command_logging
def endproposal():
    """
    Close the active dataset and move to the default inhouse proposal.
    """
    current_session.scan_saving.endproposal()


@logtools.elogbook.disable_command_logging
def enddataset():
    """
    Close the active dataset.
    """
    current_session.scan_saving.enddataset()


# Silx


@typeguard.typechecked
def silx_view(scan: typing.Union[Scan, None] = None):
    """
    Open silx view on a given scan (default last scan)
    """

    filename = None
    try:
        if scan is None:
            scan = current_session.scans[-1]
        filename = scan._scan_info["filename"]
    except IndexError:
        pass
    _launch_silx(filename)


def _launch_silx(filename: typing.Union[str, None] = None):
    args = f"{sys.executable} -m silx.app.view.main".split()
    if filename:
        args.append(filename)
    return subprocess.Popen(args)


# PyMCA


@typeguard.typechecked
def pymca(scan: typing.Union[Scan, None] = None):
    """
    Open PyMCA on a given scan (default last scan)
    """

    filename = None
    try:
        if scan is None:
            scan = current_session.scans[-1]
        filename = scan._scan_info["filename"]
    except IndexError:
        pass
    _launch_pymca(filename)


def _launch_pymca(filename: typing.Union[str, None] = None):
    args = f"{sys.executable} -m PyMca5.PyMcaGui.pymca.PyMcaMain".split()
    if filename:
        args.append(filename)
    return subprocess.Popen(args)


@logtools.elogbook.disable_command_logging
def elog_add(index=-1):
    """
    Send to the logbook given cell output and the print that was
    performed during the elaboration.
    Only a fixed size of output are kept in memory (normally last 20).

    Args:
        index (int): Index of the cell to be sent to logbook, can
                     be positive reflecting the prompt index
                     or negative.
                     Default is -1 (previous cell)

    Example:
        BLISS [2]: diode
          Out [2]: 'diode` counter info:
                     counter type = sampling
                     sampling mode = MEAN
                     fullname = simulation_diode_sampling_controller:diode
                     unit = None
                     mode = MEAN (1)

        BLISS [3]: elog_add()  # sends last output from diode
    """
    from bliss.shell.cli.repl import BlissRepl

    try:
        comment = BlissRepl().app.output[index]
    except IndexError:
        logtools.user_warning(f"Cell output [{index}] does not exist")
    else:
        logtools.elogbook.comment(comment)


@logtools.elogbook.disable_command_logging
def lprint(*args, **kw):
    elog_print(*args, **kw)
    logtools.user_warning(
        "message is send but use 'elog_print' instead of 'lprint' in the future"
    )


@logtools.elogbook.disable_command_logging
def ladd(*args, **kw):
    elog_add(*args, **kw)
    logtools.user_warning(
        "message is send but use 'elog_add' instead of 'ladd' in the future"
    )
