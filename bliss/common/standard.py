# -*- coding: utf-8 -*-

"""
Standard bliss macros (:func:`~bliss.common.standard.wa`, \
:func:`~bliss.common.standard.mv`, etc)
"""
from bliss.common import scans
from bliss.common.scans import *

from bliss.common.task_utils import cleanup, error_cleanup

__all__ = ['wa', 'wm', 'sta', 'mv', 'umv', 'mvr', 'umvr', 'move',
           'prdef', 'set_log_level', 'sync'] + scans.__all__ + \
           ['cleanup', 'error_cleanup']

import inspect
import logging
import functools
import gevent

from six import print_
from gevent import sleep
from tabulate import tabulate
from bliss.common.utils import OrderedDict

from bliss import setup_globals

from bliss.common.axis import Axis

from bliss.config.static import get_config

from bliss.common.motor_group import Group


_ERR = '!ERR'
_MAX_COLS = 9
_MISSING_VAL = '-----'
_FLOAT_FORMAT = '.05f'


_log = logging.getLogger('bliss.standard')


def __get_objects_iter(*names_or_objs):
    cfg = get_config()
    for i in names_or_objs:
        if isinstance(i, (str, unicode)):
            i = cfg.get(i)
        yield i


def __get_objects_type_iter(typ):
    for name in dir(setup_globals):
        elem = getattr(setup_globals, name)
        if isinstance(elem, typ):
            yield elem


__get_axes_iter = functools.partial(__get_objects_type_iter, Axis)


def __get_axes_names_iter():
    for axis in __get_axes_iter():
        yield axis.name


def __safe_get(obj, member, on_error=_ERR):
    try:
        return getattr(obj, member)()
    except Exception as e:
        return on_error


def __tabulate(data, **kwargs):
    kwargs.setdefault('headers', 'firstrow')
    kwargs.setdefault('floatfmt', _FLOAT_FORMAT)
    kwargs.setdefault('numalign', 'right')

    return str(tabulate(data, **kwargs))


def sync(*axes):
    """
    Forces axes synchronization with the hardware

    Args:
        axes: list of axis objects or names. If no axis is given, it syncs all
              all axes present in the session
    """
    if axes:
        axes = __get_objects_iter(*axes)
    else:
        axes = __get_axes_iter()
    for axis in axes:
        axis.sync_hard()


def wa(**kwargs):
    """
    Displays all position positions (Where All) in both user and dial units
    """
    max_cols = kwargs.get('max_cols', _MAX_COLS)
    err = kwargs.get('err', _ERR)
    get = functools.partial(__safe_get, on_error=err)

    print_("Current Positions (user, dial)")
    header, pos, dial = [], [], []
    tables = [(header, pos, dial)]
    tasks = list()
    def request(axis):
        return axis.name,get(axis, "position"),get(axis, "dial")
    for axis in __get_axes_iter():
        tasks.append(gevent.spawn(request,axis))

    for task in tasks:
        axis_name,position,dial_position = task.get()
        if len(header) == max_cols:
            header, pos, dial = [], [], []
            tables.append((header, pos, dial))
        header.append(axis_name)
        pos.append(position)
        dial.append(dial_position)

    for table in tables:
        print_()
        print_(__tabulate(table))


def wm(*axes, **kwargs):
    """
    Displays information (position - user and dial, limits) of the given axes

    Args:
        axis (~bliss.common.axis.Axis): motor axis
    """
    if not axes:
        print_('need at least one axis name/object')
        return
    max_cols = kwargs.get('max_cols', _MAX_COLS)
    err = kwargs.get('err', _ERR)
    get = functools.partial(__safe_get, on_error=err)

    header = [""]
    User, high_user, user, low_user = ["User"], [" High"], [" Current"], [" Low"]
    Dial, high_dial, dial, low_dial = ["Dial"], [" High"], [" Current"], [" Low"]
    tables = [(header, User, high_user, user, low_user,
               Dial, high_dial, dial, low_dial)]
    for axis in __get_objects_iter(*axes):
        low, high = __safe_get(axis, "limits", on_error=(err, err))
        if len(header) == max_cols:
            header = [None]
            User, high_user, user, low_user = ["User"], [" High"], [" Current"], [" Low"]
            Dial, high_dial, dial, low_dial = ["Dial"], [" High"], [" Current"], [" Low"]
            tables.append((header, User, high_user, user, low_user,
                           Dial, high_dial, dial, low_dial))
        header.append(axis.name)
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
        print_(__tabulate(table))


def stm(*axes):
    """Displays axis state (not implemented yet!)"""
    raise NotImplementedError


def sta():
    """Displays state information about all axes"""
    global __axes
    table = [("Axis", "Status")]
    table += [(axis.name, __safe_get(axis, "state", "<status not available>"))
              for axis in __get_axes_iter()]
    print_(__tabulate(table))


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


def __row_positions(positions, motors, fmt, sep=' '):
    positions = [positions[m] for m in motors]
    return __row(positions, fmt, sep='  ')


def __row(cols, fmt, sep=' '):
    return sep.join([format(col, fmt) for col in cols])


def __umove(*args, **kwargs):
    kwargs['wait'] = False
    group, motor_pos = __move(*args, **kwargs)
    with error_cleanup(group.stop):
        motor_names = [axis.name for axis in motor_pos]
        col_len = max(max(map(len, motor_names)), 8)
        hfmt = '^{width}'.format(width=col_len)
        rfmt = '>{width}.03f'.format(width=col_len)
        print_()
        print_(__row(motor_names, hfmt, sep='  '))

        while group.is_moving:
            positions = group.position()
            row = __row_positions(positions, motor_pos, rfmt, sep='  ')
            print_("\r" + row, end='', flush=True)
            sleep(0.1)
        # print last time for final positions
        positions = group.position()
        row = __row_positions(positions, motor_pos, rfmt, sep='  ')
        print_("\r" + row, end='', flush=True)
        print_()

    return group, motor_pos


def __move(*args, **kwargs):
    wait, relative = kwargs.get('wait', True), kwargs.get('relative', False)
    motor_pos = OrderedDict()
    for m, p in zip(__get_objects_iter(*args[::2]), args[1::2]):
        motor_pos[m] = p
    group = Group(*motor_pos.keys())
    group.move(motor_pos, wait=wait, relative=relative)

    return group, motor_pos

def prdef(obj_or_name):
    """
    Shows the text of the source code for an object or the name of an object.
    """
    if isinstance(obj_or_name, (str, unicode)):
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

    fname = inspect.getfile(obj)
    lines, line_nb = inspect.getsourcelines(obj)

    if name == real_name:
        header = "'{0}' is defined in:\n{1}:{2}\n". \
                 format(name, fname, line_nb)
    else:
        header = "'{0}' is an alias for '{1}' which is defined in:\n{2}:{3}\n". \
                 format(name, real_name, fname, line_nb)
    print_(header)
    print_(''.join(lines))


def _check_log_level(level):
    if isinstance(level, (int, long)):
        rv = level
    else:
        rv = getattr(logging, level.upper())
    return rv

def set_log_level(level):
    logging.root.setLevel(_check_log_level(level))
        
