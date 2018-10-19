# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
from gevent import GreenletExit

from louie import dispatcher
from louie import robustapply
from louie import saferef


if not hasattr(robustapply, "_robust_apply"):
    # patch robustapply.robust_apply to display exceptions, but to ignore them
    # this makes 'dispatcher.send' to continue on exceptions, which is
    # the behaviour we want ; it's not because a receiver doesn't handle a
    # signal properly that the whole chain should stop
    robustapply._robust_apply = robustapply.robust_apply

    def __my_robust_apply(*args, **kwargs):
        try:
            return robustapply._robust_apply(*args, **kwargs)
        except GreenletExit:
            raise
        except:
            sys.excepthook(*sys.exc_info())

    robustapply.robust_apply = __my_robust_apply
    del __my_robust_apply


def send(sender, signal, *args, **kwargs):
    dispatcher.send(signal, sender, *args, **kwargs)


def connect(sender, signal, callback):
    dispatcher.connect(callback, signal, sender)


def disconnect(sender, signal, callback):
    try:
        dispatcher.disconnect(callback, signal, sender)
    except Exception:
        pass
