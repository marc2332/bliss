# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Standard bliss macros (:func:`~bliss.common.standard.wa`, \
:func:`~bliss.common.standard.mv`, etc)
"""
from collections import namedtuple
import functools
import inspect
import contextlib
import gevent
import sys

from bliss import global_map, global_log, current_session
from bliss.common import scans
from bliss.common.scans import *
from bliss.common.plot import plot
from bliss.common.soft_axis import SoftAxis
from bliss.common.counter import SoftCounter
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common import cleanup as cleanup_mod
from bliss.common.logtools import user_print, disable_user_output
from bliss.common.interlocks import interlock_state
from bliss.controllers.motors import esrf_undulator
from bliss.config.channels import clear_cache

__all__ = (
    [
        "iter_axes_state_all",
        "iter_axes_state",
        "iter_axes_position_all",
        "iter_axes_position",
        "iter_counters",
        "mv",
        "mvr",
        "mvd",
        "mvdr",
        "move",
        "sync",
        "interlock_state",
        "reset_equipment",
    ]
    + scans.__all__
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
    user_print("Forcing axes synchronization with hardware")
    if axes:
        axes = global_map.get_axis_objects_iter(*axes)
    else:
        axes = global_map.get_axes_iter()

    for axis in axes:
        try:
            axis.sync_hard()
        except Exception as exc:
            try:
                raise RuntimeError(
                    f"Synchronization error for axis '{axis.name}'"
                ) from exc
            except Exception:
                sys.excepthook(*sys.exc_info())


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

    Example:

    .. code-block::

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
        axis_name = global_map.alias_or_name(axis)
        axis_state = safe_get(axis, "state", on_error=err)
        if axis.disabled or "DISABLED" in axis_state:
            axis_name += " *DISABLED*"
        user_low_limit, user_high_limit = safe_get(axis, "limits", on_error=(err, err))
        user_position = get(axis, "position")
        offset = safe_get(axis, "offset", on_error=float("nan"))
        dial_low_limit, dial_high_limit = safe_get(
            axis, "dial_limits", on_error=(err, err)
        )
        dial_position = get(axis, "dial")
        unit = axis.config.get("unit", default=None)

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


def mvd(*args):
    """
    Moves given axes to given absolute dial positions

    Arguments are interleaved axis and respective relative target position.
    """
    # __move_dial(*args)
    __move(*args, dial=True)


def mvdr(*args):
    """
    Moves given axes to given relative dial positions

    Arguments are interleaved axis and respective relative target position.
    """
    __move(*args, relative=True, dial=True)


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
    wait, relative, dial = (
        kwargs.get("wait", True),
        kwargs.get("relative", False),
        kwargs.get("dial", False),
    )

    motor_pos = dict()
    for m, p in zip(global_map.get_axis_objects_iter(*args[::2]), args[1::2]):
        motor_pos[m] = m.dial2user(p) if dial and not relative else p
    group = Group(*motor_pos.keys())
    group.move(motor_pos, wait=wait, relative=relative)

    return group, motor_pos


def iter_counters(counters=None):
    """
    Return a dict of counters
    """
    counters_dict = dict()
    shape = ["0D", "1D", "2D"]
    if counters is None:
        counters = global_map.get_counters_iter()

    for cnt in counters:
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


def wid():
    """ Print the list of undulators defined in the session and their
    positions.
    Print all axes of the ID device server.
    """
    data = iter_axes_position_all()
    for axis_name, axis_unit, position, dial_position in data:
        _ = position

    ID_DS_list = esrf_undulator.get_all()

    undu_str = ""
    for id_ds in ID_DS_list:
        undu_str += "\n    ---------------------------------------\n"
        undu_str += f"    ID Device Server {id_ds.ds_name}\n"

        power = f"{id_ds.device.Power:.3f}"
        max_power = f"{id_ds.device.MaxPower:.1f}"
        power_density = f"{id_ds.device.PowerDensity:.3f}"
        max_power_density = f"{id_ds.device.MaxPowerDensity:.1f}"

        undu_str += f"            Power: {power} /  {max_power}  KW\n"
        undu_str += (
            f"    Power density: {power_density} / {max_power_density}  KW/mr2\n\n"
        )

        for undu_axis in id_ds.axis_info:
            undu_axis.controller.get_axis_info(undu_axis)  # update info

            uinfo = undu_axis.controller.axis_info[undu_axis]

            if uinfo["is_revolver"]:
                undu_type = " - Revolver"
            else:
                undu_type = " "

            able = "DISABLED" if "DISABLED" in undu_axis.state else "ENABLED"
            upos = (
                "          " if able == "DISABLED" else f"GAP:{undu_axis.position:5.3f}"
            )
            undu_str += f"    {undu_axis.name} - {upos} - {able} {undu_type} \n"

    return undu_str


@contextlib.contextmanager
def rockit(motor, total_move):
    """
    Rock an axis from it's current position +/- total_move/2.
    Usage example:

    .. code-block:: python

        with rockit(mot1, 10):
             ascan(mot2,-1,1,10,0.1,diode)
             amesh(....)
    """
    if motor.is_moving:
        raise RuntimeError(f"Motor {motor.name} is moving")

    lower_position = motor.position - (total_move / 2)
    upper_position = motor.position + (total_move / 2)
    # Check limits
    motor._get_motion(lower_position)
    motor._get_motion(upper_position)

    def rock():
        with disable_user_output():
            while True:
                motor.move(lower_position)
                motor.move(upper_position)

    with cleanup_mod.cleanup(motor, restore_list=(cleanup_mod.axis.POS,)):
        rock_task = gevent.spawn(rock)
        try:
            yield
        finally:
            rock_task.kill()
            rock_task.get()


def reset_equipment(*devices):
    """
    This command will force all devices passed as argument to be reset
    For now we just force an re-initialization on next call.
    """
    device_to_reset = set()
    for dev in devices:
        device_to_reset.add(dev)
        try:
            ctrl = dev.controller
        except AttributeError:
            pass
        else:
            device_to_reset.add(ctrl)
    # clear controller cache
    clear_cache(*device_to_reset)
    # Maybe in future it'll be good to close the connection and do other things...
