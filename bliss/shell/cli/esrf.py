# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss ESRF machine status bar"""

from os import environ
from datetime import timedelta
from collections import namedtuple
from bliss.common.tango import DeviceProxy, AttrQuality, DevState

from prompt_toolkit.token import Token

from bliss.common.session import get_current as current_session

from .layout import StatusToken, Separator


BEAMLINE = environ.get("BEAMLINENAME", "ID99")
BEAMLINE_TYPE, BEAMLINE_NUMBER = "", "00"
for i, c in enumerate(BEAMLINE):
    if c.isdigit():
        BEAMLINE_TYPE = BEAMLINE[:i]
        BEAMLINE_NUMBER = BEAMLINE[i:]
        break

FE_DEVICE = "orion:10000/fe/{0}/{1}".format(BEAMLINE_TYPE, BEAMLINE_NUMBER)
ID_DEVICE = "orion:10000/id/id/{0}".format(BEAMLINE_NUMBER)
SS_DEVICE = "id{0}/bsh/1".format(BEAMLINE_NUMBER)  # safety shutter

Attribute = namedtuple("Attribute", "label attr_name unit display")


QMAP = {
    AttrQuality.ATTR_VALID: StatusToken.Ok,
    AttrQuality.ATTR_WARNING: StatusToken.Warning,
    AttrQuality.ATTR_ALARM: StatusToken.Alarm,
    AttrQuality.ATTR_CHANGING: StatusToken.Changing,
}


def tango_value(attr, value):
    if (
        value is None
        or value.has_failed
        or value.is_empty
        or value.quality == AttrQuality.ATTR_INVALID
    ):
        token, v = StatusToken.Error, "-----"
    elif attr.display is None:
        token, v = QMAP[value.quality], value.value
    else:
        token, v = attr.display(value)
    return token, v


class DeviceStatus(object):

    attributes = ()

    def __init__(self, device, attributes=None):
        if attributes is not None:
            self.attributes = attributes
        self.device = DeviceProxy(device)

    def __call__(self, cli):
        n = len(self.attributes)
        try:
            values = self.device.read_attributes([a.attr_name for a in self.attributes])
        except Exception as e:
            values = n * [None]
        result = []
        for i, (attr, value) in enumerate(zip(self.attributes, values)):
            if i > 0:
                result.append(Separator)
            token, value = tango_value(attr, value)
            if cli.python_input.bliss_bar_format != "compact":
                result.append((StatusToken, attr.label))
            value = "{0}{1}".format(value, attr.unit)
            result.append((token, value))
        return result


class FEStatus(DeviceStatus):
    def decode_fe_state(value):
        lvalue = value.value.lower()
        if "open" in lvalue:
            return Token.Toolbar.Status.Open, "OPEN"
        elif "close" in lvalue:
            return Token.Toolbar.Status.Close, "CLOSED"
        elif "fault" in lvalue:
            return Token.Toolbar.Status.Error, "FAULT"
        return QMAP[value.quality], value.value

    current = Attribute(
        "SRCurr: ",
        "SR_Current",
        "mA",
        lambda x: (QMAP[x.quality], "{0:07.3f}".format(x.value)),
    )
    lifetime = Attribute(
        "Lifetime: ",
        "SR_Lifetime",
        "",
        lambda x: (QMAP[x.quality], str(timedelta(seconds=max(x.value, 0)))),
    )
    mode = Attribute("Mode: ", "SR_Filling_Mode", "", None)
    refill = Attribute(
        "Refill in ",
        "SR_Refill_Countdown",
        "",
        lambda x: (QMAP[x.quality], str(timedelta(seconds=max(x.value, 0)))),
    )
    state = Attribute("FE: ", "FE_State", "", decode_fe_state)
    message = Attribute("", "SR_Operator_Mesg", "", None)

    attributes = current, lifetime, mode, refill, state, message

    def __init__(self, device=FE_DEVICE, **kwargs):
        super(FEStatus, self).__init__(device, **kwargs)


class IDStatus(DeviceStatus):
    def __init__(self, device=ID_DEVICE, **kwargs):
        super(IDStatus, self).__init__(device, **kwargs)
        session = current_session()
        if session:
            name = " " + session.name.upper()
        else:
            name = ""
        self.title = "ESRF-{beamline}{session}".format(beamline=BEAMLINE, session=name)

    def __call__(self, cli):
        if cli.python_input.bliss_session:
            session = " " + cli.python_input.bliss_session.name.upper()
        else:
            session = ""
        return [(Token.Toolbar.Status.Name, self.title), Separator] + super(
            IDStatus, self
        ).__call__(cli)


class SafetyShutterStatus(DeviceStatus):
    def decode_state(value):
        state = value.value
        if state == DevState.OPEN:
            return Token.Toolbar.Status.Open, "OPEN"
        elif state == DevState.CLOSE:
            return Token.Toolbar.Status.Close, "CLOSED"
        elif state == DevState.FAULT:
            return Token.Toolbar.Status.Error, "FAULT"
        elif state == DevState.DISABLE:
            return Token.Toolbar.Status.Warning, "DISABLED"
        return QMAP[value.quality], str(state)

    state = Attribute("SS: ", "State", "", decode_state)

    attributes = (state,)

    def __init__(self, device=SS_DEVICE, **kwargs):
        super(SafetyShutterStatus, self).__init__(device, **kwargs)
