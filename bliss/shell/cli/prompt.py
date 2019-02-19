# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss prompt"""

import time

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

    def in_prompt(self):
        return [
            ("class:in", self.prompt_label),
            ("class:in", " ["),
            ("class:in.number", "%s" % self.current_statement_index),
            ("class:in", "]: "),
        ]

    def in2_prompt(self, width):
        return [("class:in", "...: ".rjust(width))]

    def out_prompt(self,):
        return [
            ("class:out", "{0:>{width}}".format("Out", width=len(self.prompt_label))),
            ("class:out", " ["),
            ("class:out.number", "%s" % self.current_statement_index),
            ("class:out", "]:"),
            ("", " "),
        ]
