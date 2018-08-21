# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss prompt"""

import time

from prompt_toolkit.token import Token
from ptpython.prompt_style import PromptStyle

__all__ = ("BlissPrompt",)


class BlissPrompt(PromptStyle):
    """
    A prompt resembling the IPython prompt.

    To activate it, simply set it in the shell configure method:

    def configure(repl):
        repl.prompt_style = 'bliss'
    """

    def __init__(self, python_input, prompt_label=None):
        self.python_input = python_input
        self._prompt_label = prompt_label

    @property
    def prompt_label(self):
        return self._prompt_label or self.python_input.bliss_prompt_label

    @property
    def current_statement_index(self):
        return self.python_input.current_statement_index

    def in_tokens(self, cli):
        return [
            (Token.In, self.prompt_label),
            (Token.In, " ["),
            (Token.In.Number, "%s" % self.current_statement_index),
            (Token.In, "]: "),
        ]

    def in2_tokens(self, cli, width):
        return [(Token.In, "...: ".rjust(width))]

    def out_tokens(self, cli):
        return [
            (Token.Out, "{0:>{width}}".format("Out", width=len(self.prompt_label))),
            (Token.Out, " ["),
            (Token.Out.Number, "%s" % self.current_statement_index),
            (Token.Out, "]:"),
            (Token, " "),
        ]
