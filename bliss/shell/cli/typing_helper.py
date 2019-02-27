# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss typing helper to serve people that like to type commands as they did in spec"""

import jedi
import re

from prompt_toolkit.validation import ValidationError
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters import has_focus
from prompt_toolkit.enums import DEFAULT_BUFFER

from ptpython.python_input import PythonValidator


class TypingHelper(object):
    def __init__(self, blissrepl):
        self.validator = PythonValidator()
        self.add_helper_key_binding(blissrepl)

    def is_float_str(self, s):
        return s.lstrip("-").replace(".", "", 1).isdigit()

    def add_helper_key_binding(self, repl):
        @repl.add_key_binding(" ")
        def _(event):
            """
            add '(' and ',' instead of 'space' if appropriate in the command-line current context
            """
            text = repl.default_buffer.text
            curs_pos = repl.default_buffer.cursor_position
            if curs_pos == len(text) & len(text) > 0:
                ji = jedi.Interpreter(
                    source=text, namespaces=[repl.get_locals(), repl.get_globals()]
                )
                cs = ji.call_signatures()

                text_plus_open_bracket = text + "("
                ji_plus_open_bracket = jedi.Interpreter(
                    source=text_plus_open_bracket,
                    namespaces=[repl.get_locals(), repl.get_globals()],
                )
                cs_plus_open_bracket = ji_plus_open_bracket.call_signatures()

                # add open bracket or '
                if len(cs) < len(cs_plus_open_bracket):
                    repl.default_buffer.insert_text("(")
                elif len(cs) > len(cs_plus_open_bracket):
                    doc = Document(text=text + ")", cursor_position=curs_pos)
                    try:
                        self.validator.validate(doc)
                        repl.default_buffer.insert_text(",")

                    except ValidationError as e:  # e.g. inside string ... print('bla bla
                        if e.message == "Syntax Error":
                            repl.default_buffer.insert_text(" ")

                elif self.is_float_str(re.split(",|\(", text)[-1]):  # e.g. ascan(m0,1
                    repl.default_buffer.insert_text(",")
                else:
                    repl.default_buffer.insert_text(" ")
            else:
                repl.default_buffer.insert_text(" ")

        @repl.add_key_binding(Keys.Enter, filter=has_focus(DEFAULT_BUFFER))
        def _(event):
            self._check_terminating_bracket(repl, event)

            # looks still like a hack but I did not find
            # another way to call the original handler for 'enter' yet
            h = [
                h
                for h in event.cli.key_processor._get_matches([KeyPress(Keys.Enter)])
                if h.handler.__qualname__ == "load_python_bindings.<locals>._"
            ][0]
            event.cli.key_processor._call_handler(
                h, key_sequence=[KeyPress(Keys.Enter)]
            )

        @repl.add_key_binding(";")
        def _(event):
            self._check_terminating_bracket(repl, event, termination=");")

    def _check_terminating_bracket(self, repl, event, termination=")"):
        """
        add ')' if it solves 'Syntax Error' of the current input before passing the 'enter' event to ptpython
        
        note: in order to make this helper work for functions like wa() without arguments one has to type wa + 'space' + 'enter'
        """
        text = repl.default_buffer.text
        curs_pos = repl.default_buffer.cursor_position

        if curs_pos == len(text) & len(text) > 0:
            doc = Document(text=text, cursor_position=curs_pos)
            try:
                self.validator.validate(doc)
            except ValidationError as e:
                if e.message == "Syntax Error":

                    new_text = text + ")"
                    new_doc = Document(text=new_text, cursor_position=curs_pos + 1)

                    try:
                        self.validator.validate(new_doc)
                        repl.default_buffer.insert_text(termination)
                    except ValidationError:

                        pass
