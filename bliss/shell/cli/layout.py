# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss status bar"""

import functools

import gevent

from prompt_toolkit.token import Token
from prompt_toolkit.layout.toolbars import TokenListToolbar
from prompt_toolkit.filters import IsDone, RendererHeightIsKnown, Condition
from prompt_toolkit.layout.screen import Char

from bliss.common.axis import Axis
from bliss.config.static import get_config

__all__ = (
    "status_bar",
    "AxisStatus",
    "StatusToken",
    "Separator",
    "LabelWidget",
    "DynamicWidget",
)


StatusToken = Token.Toolbar.Status

Separator = StatusToken, " | "


class StatusToolbar(TokenListToolbar):
    """
    Bliss status toolbar.

    Example on how to add items in your setup::

        from bliss.shell.cli import configure
        from bliss.shell.layout import AxisStatus, StatusToken

        @configure
        def config(repl):
            # use compact format (means no labels)
            repl.bliss_bar_format = 'compact'

            # add the theta axis status
            repl.bliss_bar.items.append(AxisStatus('theta'))

            # add a fixed message
            repl.bliss_bar.items.append(LabelWidget('a fixed status message'))

    """

    def __init__(self, items, *args, **kwargs):
        self.items = list(items)
        self.format = kwargs.pop("format", "normal")
        get_tokens = functools.partial(self.get_tokens, self)
        super(StatusToolbar, self).__init__(get_tokens, *args, **kwargs)

    @staticmethod
    def get_tokens(bar, cli):
        items = [
            gevent.spawn(item, cli) if callable(item) else item for item in bar.items
        ]
        values = [
            item.get() if isinstance(item, gevent.Greenlet) else item for item in items
        ]
        result = []
        for i, value in enumerate(values):
            if i > 0:
                result.append(Separator)
            result.extend(value)
        return result


def status_bar(python_input, *items):
    return StatusToolbar(
        items,
        default_char=Char(token=StatusToken),
        filter=~IsDone()
        & RendererHeightIsKnown()
        & Condition(
            lambda cli: python_input.show_bliss_bar
            and python_input.bliss_bar.items
            and not python_input.show_exit_confirmation
        ),
    )


class AxisStatus(object):
    def __init__(self, axis):
        self.name = axis.name if isinstance(axis, Axis) else axis

    def __call__(self, cli):
        config = get_config()
        axis = config.get(self.name)
        label = axis.config.get("label", default=self.name)
        unit = axis.config.get("unit", default="")
        state, position = axis.state(), axis.position()

        result = []
        if cli.python_input.bliss_bar_format != "compact":
            result.append((StatusToken, label + ": "))

        if state == "MOVING":
            token = StatusToken.Changing
        else:
            token = StatusToken.Ok
        value = "{0:.4}{1}".format(position, unit)
        result.append((token, value))
        return result


class LabelWidget(object):
    def __init__(self, message):
        self._message = message

    def __call__(self, cli):
        return [(StatusToken.Label, self._message)]


class DynamicWidget(object):
    def __init__(self, func):
        self.func = func

    def __call__(self, cli):
        _ans = str(self.func())
        return [(StatusToken.Label, _ans)]
