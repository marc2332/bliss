# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss typing helper to serve people that like to type commands as they did in spec"""

import jedi
import re
import inspect

from prompt_toolkit.validation import ValidationError
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters import has_focus
from prompt_toolkit.enums import DEFAULT_BUFFER

from ptpython.python_input import PythonValidator
import bliss.shell.cli


def is_multiline(text):
    if len(text.splitlines()) > 1:
        return True
    return False


def is_property(text, repl):
    # validating a python attribute accessed with dot notation like "instance1.instance2.attribute"

    # sanitize
    sanitized = re.split(r"[^a-zA-Z0-9_\.]", text.strip())[-1]
    m = re.match(
        r"^(?P<instance_name>[A-Za-z_]([A-Za-z0-9_\.]*[A-Za-z_0-9])*)\.(?P<attr_name>([A-Z-a-z0-9_]+))$",
        sanitized,
    )
    if not m:
        return False
    if (
        m["instance_name"] not in repl.get_globals()
        and m["instance_name"] not in repl.get_locals()
    ):
        return False
    try:
        result = isinstance(
            eval(
                f"type({m['instance_name']}).{m['attr_name']}",
                repl.get_globals(),
                repl.get_locals(),
            ),
            property,
        )
    except Exception:
        return False
    else:
        return result


class TypingHelper(object):
    def __init__(self, blissrepl):
        self.validator = PythonValidator()
        self.add_helper_key_binding(blissrepl)
        self.blissrepl = blissrepl

    @property
    def is_active(self):
        return bliss.shell.cli.typing_helper_active

    def add_helper_key_binding(self, repl):
        @repl.add_key_binding(" ", filter=has_focus(DEFAULT_BUFFER))
        def _(event):
            """
            add '(' and ',' instead of 'space' if appropriate in the command-line current context
            """
            text = repl.default_buffer.text
            curs_pos = repl.default_buffer.cursor_position
            if (
                self.is_active
                and not is_multiline(text)
                and curs_pos == len(text) & len(text) > 0
                and not is_property(text, repl)
            ):
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

                # add open bracket or ,
                if self._check_callable(repl, event) and len(cs) < len(
                    cs_plus_open_bracket
                ):
                    self._check_terminating_bracket(repl, event)
                    if repl.default_buffer.text[-1] != ")":
                        repl.default_buffer.insert_text("(")
                elif len(cs) > len(cs_plus_open_bracket):
                    doc = Document(text=text + ")", cursor_position=curs_pos)
                    try:
                        self.validator.validate(doc)
                        repl.default_buffer.insert_text(",")

                    except ValidationError as e:  # e.g. inside string ... print('bla bla
                        if e.message == "Syntax Error":
                            repl.default_buffer.insert_text(" ")
                else:
                    try:  # e.g. ascan(m0,1   or ascan(run=False,1
                        tmp = re.split(r",|\(", text)[-1].strip()
                        if len(tmp) > 0 and tmp[-1] != "," and cs != []:
                            doc = Document(text=tmp, cursor_position=len(tmp))
                            self.validator.validate(doc)
                            repl.default_buffer.insert_text(",")
                        else:
                            repl.default_buffer.insert_text(" ")

                    except ValidationError as e:
                        repl.default_buffer.insert_text(" ")

            else:
                repl.default_buffer.insert_text(" ")

        @repl.add_key_binding(Keys.Enter, filter=has_focus(DEFAULT_BUFFER))
        def _(event):
            text = repl.default_buffer.text
            if (
                self.is_active
                and not is_multiline(text)
                and not is_property(text, repl)
                and not self._check_callable(repl, event)
            ):

                self._check_terminating_bracket(repl, event)
            elif (
                self.is_active
                and not is_multiline(text)
                and not is_property(text, repl)
                and self._check_callable(repl, event)
            ):
                # if is a callable without further arguments
                self._insert_parenthesis_if_noargs(repl, event)

            # looks still like a hack but I did not find
            # another way to call the original handler for 'enter' yet
            matches = event.cli.key_processor._get_matches([KeyPress(Keys.Enter)])
            # Use reverse search because forward search finds the wrong
            # load_confirm_exit-binding
            for handler in reversed(matches):
                if (
                    self.blissrepl.bliss_prompt.python_input.show_exit_confirmation
                    and handler.handler.__qualname__
                    == "load_confirm_exit_bindings.<locals>._"
                ):
                    event.cli.key_processor._call_handler(
                        handler, key_sequence=[KeyPress(Keys.Enter)]
                    )
                    break
                elif handler.handler.__qualname__ == "load_python_bindings.<locals>._":
                    event.cli.key_processor._call_handler(
                        handler, key_sequence=[KeyPress(Keys.Enter)]
                    )
                    break

        @repl.add_key_binding(";", filter=has_focus(DEFAULT_BUFFER))
        def _(event):
            text = repl.default_buffer.text
            if (
                self.is_active
                and not is_multiline(text)
                and not is_property(text, repl)
                and not self._check_callable(repl, event)
            ):
                self._check_terminating_bracket(repl, event)
            repl.default_buffer.insert_text(";")

        @repl.add_key_binding(Keys.F7, filter=has_focus(DEFAULT_BUFFER), eager=True)
        def _(event):
            """F7 will toggle typing helper"""
            bliss.shell.cli.typing_helper_active = (
                not bliss.shell.cli.typing_helper_active
            )

    def _check_terminating_bracket(self, repl, event):
        """
        add ')' if it solves 'Syntax Error' of the current input before passing the 'enter' event to ptpython
        """
        text = repl.default_buffer.text
        curs_pos = repl.default_buffer.cursor_position

        if curs_pos == len(text) & len(text) > 0 and text[-1] != ",":
            doc = Document(text=text, cursor_position=curs_pos)
            try:
                self.validator.validate(doc)
            except ValidationError as e:
                if e.message == "Syntax Error":

                    new_text = text + ")"
                    new_doc = Document(text=new_text, cursor_position=curs_pos + 1)

                    try:
                        self.validator.validate(new_doc)
                        repl.default_buffer.insert_text(")")
                    except ValidationError:

                        pass

    def _check_callable(self, repl, event):
        """callable without any parameter without default value?
        if yes: add brackets
        """
        fulltext = repl.default_buffer.text
        if ";" in fulltext:
            other_commands, text = fulltext.rsplit(";", 1)
        else:
            text = fulltext

        # Check for return only
        if len(text) == 0:
            return True

        if text[-1] == ")":
            return True

        cnt = 0
        if text[-1] == "(":
            cnt = 1
            text = text[:-1]

        # Go to end of buffer before to insert parenthesis.
        if repl.default_buffer._Buffer__cursor_position < len(fulltext):
            repl.default_buffer._set_cursor_position(len(fulltext))

        try:
            obj = repl.get_locals().get(text, None)
            if obj is None:
                obj = repl.get_globals().get(text, None)
            if obj is None and eval(
                f"callable({text})", repl.get_globals(), repl.get_locals()
            ):
                obj = eval(text, repl.get_globals(), repl.get_locals())
        except:
            return False

        if callable(obj):
            # if not self._has_positional_args(obj):
            #    repl.default_buffer.insert_text("()"[cnt:])
            return True

        return False

    def _insert_parenthesis_if_noargs(self, repl, event):
        """
        """
        fulltext = repl.default_buffer.text
        if ";" in fulltext:
            other_commands, text = fulltext.rsplit(";", 1)
        else:
            text = fulltext

        # Check for return only
        if len(text) == 0:
            return

        if text[-1] == ")":
            return

        cnt = 0
        if text[-1] == "(":
            cnt = 1
            text = text[:-1]

        # Go to end of buffer before to insert parenthesis.
        if repl.default_buffer._Buffer__cursor_position < len(fulltext):
            repl.default_buffer._set_cursor_position(len(fulltext))

        try:
            obj = repl.get_locals().get(text, None)
            if obj is None:
                obj = repl.get_globals().get(text, None)
            if obj is None and eval(
                f"callable({text})", repl.get_globals(), repl.get_locals()
            ):
                obj = eval(text, repl.get_globals(), repl.get_locals())
        except:
            return

        if callable(obj):
            if not self._has_positional_args(obj):
                repl.default_buffer.insert_text("()"[cnt:])

    def _has_positional_args(self, callable_obj):
        """any parameter without default value?"""
        try:
            for p in inspect.signature(callable_obj)._parameters.values():
                if p.kind == inspect._ParameterKind.POSITIONAL_ONLY:
                    return True
                elif (
                    p.kind == inspect._ParameterKind.POSITIONAL_OR_KEYWORD
                    and p.default is inspect._empty
                ):
                    return True
        except:
            # we get there if there is no signature e.g. print
            return True

        return False
