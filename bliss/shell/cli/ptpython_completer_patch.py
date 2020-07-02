# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Patch to modify the behavior of the ptpython PythonCompleter
The code for def signature_toolbar corresponds to ptpython version 2.0.4
"""
from ptpython.utils import get_jedi_script_from_document
from prompt_toolkit.completion import Completion


def NEWget_completions(self, document, complete_event):
    """
    Get Python completions. Hide those starting with "_" (unless user first types the underscore).
    """
    # Do Path completions
    if complete_event.completion_requested or self._complete_path_while_typing(
        document
    ):
        for c in self._path_completer.get_completions(document, complete_event):
            yield c

    # If we are inside a string, Don't do Jedi completion.
    if self._path_completer_grammar.match(document.text_before_cursor):
        return

    # Do Jedi Python completions.
    if complete_event.completion_requested or self._complete_python_while_typing(
        document
    ):
        script = get_jedi_script_from_document(
            document, self.get_locals(), self.get_globals()
        )

        if script:
            try:
                completions = script.completions()
            except TypeError:
                # Issue #9: bad syntax causes completions() to fail in jedi.
                # https://github.com/jonathanslenders/python-prompt-toolkit/issues/9
                pass
            except UnicodeDecodeError:
                # Issue #43: UnicodeDecodeError on OpenBSD
                # https://github.com/jonathanslenders/python-prompt-toolkit/issues/43
                pass
            except AttributeError:
                # Jedi issue #513: https://github.com/davidhalter/jedi/issues/513
                pass
            except ValueError:
                # Jedi issue: "ValueError: invalid \x escape"
                pass
            except KeyError:
                # Jedi issue: "KeyError: u'a_lambda'."
                # https://github.com/jonathanslenders/ptpython/issues/89
                pass
            except IOError:
                # Jedi issue: "IOError: No such file or directory."
                # https://github.com/jonathanslenders/ptpython/issues/71
                pass
            except AssertionError:
                # In jedi.parser.__init__.py: 227, in remove_last_newline,
                # the assertion "newline.value.endswith('\n')" can fail.
                pass
            except SystemError:
                # In jedi.api.helpers.py: 144, in get_stack_at_position
                # raise SystemError("This really shouldn't happen. There's a bug in Jedi.")
                pass
            except NotImplementedError:
                # See: https://github.com/jonathanslenders/ptpython/issues/223
                pass
            except Exception:
                # Supress all other Jedi exceptions.
                pass
            else:
                for c in completions:
                    if c.name.startswith("_") and c.name == c.complete:
                        continue
                    yield Completion(
                        c.name_with_symbols,
                        len(c.complete) - len(c.name_with_symbols),
                        display=c.name_with_symbols,
                    )


import ptpython.completer

ptpython.completer.PythonCompleter.get_completions = NEWget_completions
