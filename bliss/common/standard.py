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
from collections import namedtuple
import functools
import inspect

from bliss import global_map, global_log, current_session
from bliss.common import scans
from bliss.common.scans import *

from bliss.common.plot import plot
from bliss.common.soft_axis import SoftAxis
from bliss.common.counter import SoftCounter
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common import logtools
from bliss.common.logtools import *
from bliss.common.interlocks import interlock_state

__all__ = (
    [
        "iter_axes_state_all",
        "iter_axes_state",
        "iter_axes_position_all",
        "iter_axes_position",
        "iter_counters",
        "mv",
        "mvr",
        "move",
        "sync",
        "interlock_state",
    ]
    + scans.__all__
    + logtools.__all__
    + ["cleanup", "error_cleanup", "plot"]
    + ["SoftAxis", "SoftCounter"]
)


from bliss.common.motor_group import Group
from bliss.common.utils import safe_get, ErrorWithTraceback

_ERR = "!ERR"


WhereAll = namedtuple("WhereAll", "axis_name unit user_position dial_position")
WhereMotor = namedtuple(
    "WhereMotor",
    "axis_name unit user_position user_high_limit user_low_limit offset, dial_position dial_high_limit dial_low_limit",
)
StateMotor = namedtuple("StateMotor", "axis_name state")
CountersList = namedtuple("CountersList", "fullname shape prefix name alias")


def sync(*axes):
    """
    Forces axes synchronization with the hardware

    Args:
        axes: list of axis objects or names. If no axis is given, it syncs all
              all axes present in the session
    """
    lprint("Forcing axes synchronization with hardware")
    if axes:
        axes = global_map.get_axis_objects_iter(*axes)
    else:
        axes = global_map.get_axes_iter()
    for axis in axes:
        axis.sync_hard()


def iter_axes_state(*axes, read_hw=False):
    """
    Returns state information of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    for axis in global_map.get_axis_objects_iter(*axes):
        if axis.name not in current_session.env_dict:
            continue
        state = safe_get(
            axis, "state", on_error=ErrorWithTraceback(error_txt=_ERR), read_hw=read_hw
        )
        yield StateMotor(global_map.alias_or_name(axis), state)


def iter_axes_state_all(read_hw=False):
    """
    Returns state information about all axes

    Keyword Args:
        read_hw (bool): If True, force communication with hardware, otherwise
                        (default) use cached value.
    """
    return iter_axes_state(*list(global_map.get_axes_iter()), read_hw=read_hw)


def iter_axes_position_all(**kwargs):
    """
    Iterates all positions (Where All) in both user and dial units
    """
    err = kwargs.get("err", _ERR)
    for (
        axis_name,
        user_position,
        dial_position,
        unit,
    ) in global_map.get_axes_positions_iter(on_error=ErrorWithTraceback(error_txt=err)):
        if axis_name not in current_session.env_dict:
            continue
        yield WhereAll(axis_name, unit, user_position, dial_position)


def iter_axes_position(*axes, **kwargs):
    """
    Return information (position - user and dial, limits) of the given axes

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
        raise RuntimeError("need at least one axis name/object")

    err = kwargs.get("err", _ERR)
    get = functools.partial(safe_get, on_error=ErrorWithTraceback(error_txt=err))

    for axis in global_map.get_axis_objects_iter(*axes):
        # get limits in USER units.
        user_low_limit, user_high_limit = safe_get(axis, "limits", on_error=(err, err))
        offset = safe_get(axis, "offset", on_error=float("nan"))
        unit = axis.config.get("unit", default=None)
        axis_name = global_map.alias_or_name(axis)
        dial_high_limit = axis.user2dial(user_high_limit)
        dial_low_limit = axis.user2dial(user_low_limit)
        user_position = get(axis, "position")
        dial_position = get(axis, "dial")

        where_motor = WhereMotor(
            axis_name,
            unit,
            user_position,
            user_high_limit,
            user_low_limit,
            offset,
            dial_position,
            dial_high_limit,
            dial_low_limit,
        )

        yield where_motor


def mv(*args):
    """
    Moves given axes to given absolute positions

    Arguments are interleaved axis and respective absolute target position.
    Example::

        >>> mv(th, 180, chi, 90)

    See Also: move
    """
    move(*args)


def mvr(*args):
    """
    Moves given axes to given relative positions

    Arguments are interleaved axis and respective relative target position.
    Example::

        >>> mv(th, 180, chi, 90)
    """
    __move(*args, relative=True)


def move(*args, **kwargs):
    """
    Moves given axes to given absolute positions

    Arguments are interleaved axis and respective absolute target position.
    Example::

        >>> mv(th, 180, chi, 90)

    See Also: mv
    """
    __move(*args, **kwargs)


def __move(*args, **kwargs):
    wait, relative = kwargs.get("wait", True), kwargs.get("relative", False)
    motor_pos = dict()
    for m, p in zip(global_map.get_axis_objects_iter(*args[::2]), args[1::2]):
        motor_pos[m] = p
    group = Group(*motor_pos.keys())
    group.move(motor_pos, wait=wait, relative=relative)

    return group, motor_pos


def iter_counters():
    """
    Return a dict of counters
    """

    counters_dict = dict()
    shape = ["0D", "1D", "2D"]

    for cnt in global_map.get_counters_iter():
        prefix, _, short_name = cnt.fullname.rpartition(":")
        counters_dict[cnt.fullname] = (
            shape[len(cnt.shape)],
            cnt._counter_controller.name if cnt._counter_controller else prefix,
            short_name,
            global_map.aliases.get_alias(cnt),
        )
    for fullname, (shape, prefix, name, alias) in counters_dict.items():
        yield CountersList(fullname, shape, prefix, name, alias)


def info(obj):
    """
    In Bliss `__info__` is used by the command line interface (Bliss shell or Bliss repl) 
    to enquire information of the internal state of any object / controller in case it is 
    available. this info function is to be seen as equivalent of str(obj) or repr(obj) in
    this context.

    if *obj* has `__info__` implemented this `__info__` function will be called. As a fallback 
    option (`__info__` not implemented) repr(obj) is used. 
    """

    if not inspect.isclass(obj) and hasattr(obj, "__info__"):
        # this is not a violation of EAFP, this is to
        # discriminate AttributeError raised *inside* __info__ ;
        # TODO: clean with protocol
        try:
            info_str = obj.__info__()
        except Exception:
            raise
        else:
            if not isinstance(info_str, str):
                raise TypeError("__info__ must return a string")
    else:
        info_str = repr(obj)

    return info_str
