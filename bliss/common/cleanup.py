# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
__all__ = ["cleanup", "axis", "lima"]

import os
import inspect
from contextlib import contextmanager
from multiprocessing import Process
import enum
import gevent
import errno
import sys
import six

axis = enum.Enum("axis", "POS VEL ACC LIM")
lima = enum.Enum("lima", "VIDEO_LIVE")


@contextmanager
def excepthook(custom_hook=None):
    try:
        yield
    except:
        if custom_hook:
            custom_hook(*sys.exc_info())
        else:
            sys.excepthook(*sys.exc_info())


@contextmanager
def cleanup(*args, **kwargs):
    """
    This cleanup context manager can handle either device like
    Axis, Lima device, Mca device or simple cleanup function.

    All cleanup functions will be called at the end of the context.

    For Motors, this context manager would guarantee that they
    will be stopped in any case, or even returned to
    their initial position if **axis.POS** is in **restore_list**.
    You also have the possibility to restore the velocity (axis.VEL),
    the acceleration (axis.ACC) or the limits (axis.LIM).
    All motors in the context will be waited.

    For other device (mca, lima) the acquisition will be stopped
    when we leave the context

    Args:
        can be device (Axis, Lima...) or cleanup function
    """

    from .axis import Axis
    from . import motor_group

    restore_list = kwargs.pop("restore_list", list())
    error_cleanup = kwargs.pop("error_cleanup", False)
    finally_cleanup = not error_cleanup
    motors = list()
    lima_device = list()
    stoppable_device = list()
    functions = list()
    for arg in args:
        if isinstance(arg, Axis):
            motors.append(arg)
        elif type(arg).__name__ == "Lima":
            lima_device.append(arg)
        elif callable(arg):
            functions.append(arg)
        else:
            stop_methods = [
                x[0]
                for x in inspect.getmembers(arg, predicate=inspect.ismethod)
                if x[0].startswith("stop")
            ]
            if len(stop_methods) != 1:
                stop_methods = [x for x in stop_methods if x.find("acq") > -1]
                if len(stop_methods) != 1:
                    raise RuntimeError("Cannot manage this object {}".format(arg))
            stoppable_device.append(getattr(arg, stop_methods[0]))

    mot_group = motor_group.Group(*motors) if motors else None

    if axis.POS in restore_list:
        previous_motor_position = list()
        for mot in motors:
            previous_motor_position.extend((mot, mot.position()))
    if axis.VEL in restore_list:
        previous_motor_velocity = [
            (mot, mot.velocity()) for mot in motors if hasattr(mot, "velocity")
        ]
    if axis.ACC in restore_list:
        previous_motor_acc = [
            (mot, mot.acceleration()) for mot in motors if hasattr(mot, "acceleration")
        ]
    if axis.LIM in restore_list:
        previous_motor_limits = [
            (mot, mot.limits()) for mot in motors if hasattr(mot, "limits")
        ]
    try:
        yield
    except:
        finally_cleanup = True
        raise
    finally:
        if finally_cleanup:
            exceptions = list()
            for func in functions:
                try:
                    func(**kwargs)
                except Exception as exc:
                    exceptions.append(exc)

            for stop_method in stoppable_device:
                try:
                    stop_method()
                except Exception as exc:
                    exceptions.append(exc)

            for ldev in lima_device:
                try:
                    ldev.stopAcq()
                    if lima.VIDEO_LIVE in restore_list:
                        pass  # todo
                except Exception as exc:
                    exceptions.append(exc)

            if mot_group is not None:
                gevent.joinall([gevent.spawn(motor.stop) for motor in motors])
                if axis.VEL in restore_list:
                    gevent.joinall(
                        [
                            gevent.spawn(motor.velocity, value)
                            for motor, value in previous_motor_velocity
                        ]
                    )
                if axis.ACC in restore_list:
                    gevent.joinall(
                        [
                            gevent.spawn(motor.acceleration, value)
                            for motor, value in previous_motor_acc
                        ]
                    )
                if axis.LIM in restore_list:
                    gevent.joinall(
                        [
                            gevent.spawn(motor.limits, *values)
                            for motor, values in previous_motor_limits
                        ]
                    )
                if axis.POS in restore_list:
                    mot_group.move(*previous_motor_position)

            if exceptions:
                if len(exceptions) == 1:
                    raise exceptions[0]
                else:
                    msg = "\n".join((str(e) for e in exceptions))
                    raise RuntimeError("Multiple cleanup errors\n{}".format(msg))


def error_cleanup(*args, **kwargs):
    """
    cleanup executed in case of exception.
    for more detail see **cleanup**
    """
    kwargs.setdefault("error_cleanup", True)
    return cleanup(*args, **kwargs)


class post_mortem_cleanup(object):
    """ This cleanup call the cleanup functions only if your programm crash.
    """

    def __init__(self, *args, **keys):
        self._error_funcs = args
        self._keys = keys
        self._process = None

    def __enter__(self):
        self._read, self._write = os.pipe()
        self.p = Process(target=self._run)
        self.p.start()
        os.close(self._read)
        return self

    def __exit__(self, *args):
        os.write(self._write, "|")
        self.p.join()
        os.close(self._write)

    def _run(self):
        os.close(self._write)
        while True:
            try:
                value = os.read(self._read, 1024)
            except OSError as err:
                if err.errno == errno.EAGAIN:
                    continue

            # pipe was closed, trigger the cleanup
            if not value:
                for error_func in self._error_funcs:
                    try:
                        error_func(**self._keys)
                    except:
                        sys.excepthook(*sys.exc_info())

            sys.exit(0)


@contextmanager
def capture_exceptions(raise_index=-1, excepthook=None):
    """A context manager to capture and manage multiple exceptions.

    Usage:

        with capture_exceptions() as capture:
            with capture():
                do_A()
            with capture():
                do_B()
            with capture():
                do_C()

    The inner contexts protect the execution by capturing any exception
    raised. This allows the next contexts to run. When leaving the main
    context, the last exception is raised, if any. If the `raise_index`
    argument is set to `0`, the first exception is raised instead. This
    behavior can also be disabled by setting `raise_index` to None. The
    other exceptions are processed through the given excepthook, which
    defaults to `sys.excepthook`. A list containing the information about
    the raised exception can be retreived using the `exception_infos`
    attribute of the `capture` object or the raised exception.
    """
    assert raise_index in (0, -1, None)

    if excepthook is None:
        excepthook = sys.excepthook

    @contextmanager
    def capture():
        try:
            yield
        except BaseException:
            infos.append(sys.exc_info())
            if excepthook:
                if raise_index is None or raise_index == 0 and len(infos) > 1:
                    excepthook(*infos[-1])
                elif raise_index == -1 and len(infos) > 1:
                    excepthook(*infos[-2])

    infos = capture.exception_infos = capture.failed = []
    with capture():
        yield capture

    if not infos or raise_index is None:
        return

    etype, value, tb = infos[raise_index]
    value.exception_infos = infos
    six.reraise(etype, value, tb)
