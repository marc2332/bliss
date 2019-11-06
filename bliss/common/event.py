# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
from gevent import GreenletExit

from louie import dispatcher
from louie.dispatcher import get_receivers
from louie import robustapply
from louie import saferef
from louie import Any


def _get_sender(sender):
    try:
        sender = sender.__wrapped__
    except AttributeError:
        pass
    return sender


def send(sender, signal, *args, **kwargs):
    sender = _get_sender(sender)
    dispatcher.send(signal, sender, *args, **kwargs)


def connect(sender, signal, callback):
    sender = _get_sender(sender)
    if signal is Any:
        dispatcher.connect(callback, sender=sender)
    else:
        dispatcher.connect(callback, signal, sender)


def disconnect(sender, signal, callback):
    sender = _get_sender(sender)
    try:
        if signal is Any:
            dispatcher.disconnect(callback, sender=sender)
        else:
            dispatcher.disconnect(callback, signal, sender)
    except Exception:
        pass
