# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
from gevent import GreenletExit

from louie import dispatcher
from louie import robustapply
from louie import saferef


def send(sender, signal, *args, **kwargs):
    dispatcher.send(signal, sender, *args, **kwargs)


def connect(sender, signal, callback):
    dispatcher.connect(callback, signal, sender)


def disconnect(sender, signal, callback):
    try:
        dispatcher.disconnect(callback, signal, sender)
    except Exception:
        pass
