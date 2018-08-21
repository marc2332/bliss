# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss shell user interface style"""

from ptpython.style import get_all_ui_styles
from prompt_toolkit.token import Token

__all__ = ("bliss_ui_style",)


_default = get_all_ui_styles()["default"]

bliss_ui_style = dict(_default)
bliss_ui_style.update(
    {
        Token.Toolbar.Status.Name: "bg:#0000ff #ffffff bold",
        Token.Toolbar.Status.Label: "bg:#222222 #ffffff bold",
        Token.Toolbar.Status.Ok: "bg:#222222 #ffffff",
        Token.Toolbar.Status.Warning: "bg:#ffa500 #ffffff",
        Token.Toolbar.Status.Alarm: "bg:#aa0000 #ffffff",
        Token.Toolbar.Status.Error: "bg:#ff00ff #ffffff",
        Token.Toolbar.Status.Changing: "bg:#3333ff #ffffff",
        Token.Toolbar.Status.Open: "bg:#00aa00 #ffffff",
        Token.Toolbar.Status.Close: "bg:#aa0000 #ffffff",
    }
)
