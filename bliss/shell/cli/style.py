# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

__all__ = ("bliss_ui_style", "bliss_code_style")

"""Bliss shell user interface style"""

from ptpython.style import default_ui_style
from prompt_toolkit.styles import Style

_bliss_ui_style = dict(default_ui_style)
_bliss_ui_style.update(
    {
        "signature-toolbar.current-name": "bg:#44bbbb #960000 bold",
        "signature-toolbar.operator": "bg:#44bbbb #000000 bold",
    }
)

bliss_ui_style = Style.from_dict(_bliss_ui_style)


"""Bliss shell code style"""

from pygments.styles import get_style_by_name
from prompt_toolkit.styles import pygments as pt_pygments
from pygments.token import Token

_bliss_code_style = get_style_by_name("default").styles

# Change some colors to have something readable on dark and light backgrounds
_bliss_code_style[Token.Name.Function] = "#0085A1"
_bliss_code_style[Token.Name.Class] = "bold #0085A1"
_bliss_code_style[Token.Name.Namespace] = "bold #0085A1"
_bliss_code_style[Token.Literal.Number] = "bold #008700"
_bliss_code_style[Token.Literal.Number] = "bold #008700"
_bliss_code_style[Token.Operator] = ""
_bliss_code_style[Token.Name.Variable] = "#AA6699"  # __class__
_bliss_code_style[Token.Operator.Word] = "bold #AA6699"  # and/in/not
_bliss_code_style[Token.Name.Decorator] = "#AA6699"  # decorator


# Creates bliss style
bliss_code_style = pt_pygments.style_from_pygments_dict(_bliss_code_style)

"""
Example to test:

@tutu
class MyClass():
    def __init__():
        load_script('demod.py')
        if AA and not BB:
            type(e.titi)
            print('\033[31;42m salut')
        from NameSpace import FF
        pass
    def my_func():
        PythonRepl.__class__();print('dddD') ; # fdslkfjsd
        for ii in ['aa', 'bb', 'cc']:
            print(ii)
        try:
            aascan(mot1,13.2+22*2/2-1)
        except KeyboardInterrupt:
            print('basta')
    print('bye')
"""
