# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Patch to modify the behavior of the ptpython signature_toolbar
The code for def signature_toolbar corresponds to ptpython version 2.0.4
"""
from inspect import _ParameterKind as ParameterKind
from prompt_toolkit.layout.containers import Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from ptpython.filters import HasSignature, ShowSignature, ShowSidebar
from prompt_toolkit.filters import is_done
from prompt_toolkit.formatted_text.base import StyleAndTextTuples


def NEWsignature_toolbar(python_input):
    """
    Return the `Layout` for the signature.
    """

    def get_text_fragments() -> StyleAndTextTuples:
        result: StyleAndTextTuples = []
        append = result.append
        Signature = "class:signature-toolbar"

        if python_input.signatures:
            sig = python_input.signatures[0]  # Always take the first one.

            append((Signature, " "))
            try:
                append((Signature, sig.name))
            except IndexError:
                # Workaround for #37: https://github.com/jonathanslenders/python-prompt-toolkit/issues/37
                # See also: https://github.com/davidhalter/jedi/issues/490
                return []

            append((Signature + ".operator", "("))  ### PATCHED HERE

            got_positional_only = False
            got_keyword_only = False

            for i, p in enumerate(sig.parameters):
                # Detect transition between positional-only and not positional-only.
                if p.kind == ParameterKind.POSITIONAL_ONLY:
                    got_positional_only = True
                if got_positional_only and p.kind != ParameterKind.POSITIONAL_ONLY:
                    got_positional_only = False
                    append((Signature, "/"))
                    append((Signature + ".operator", ", "))  ### PATCHED HERE

                if not got_keyword_only and p.kind == ParameterKind.KEYWORD_ONLY:
                    got_keyword_only = True
                    append((Signature, "*"))
                    append((Signature + ".operator", ", "))  ### PATCHED HERE

                sig_index = getattr(sig, "index", 0)

                description = p.description.split("param ")[-1]  ### PATCHED HERE
                if i == sig_index:
                    # Note: we use `_Param.description` instead of
                    #       `_Param.name`, that way we also get the '*' before args.
                    append(
                        (Signature + ".current-name", str(description))
                    )  ### PATCHED HERE
                else:
                    append((Signature, str(description)))  ### PATCHED HERE

                if p.default:
                    # NOTE: For the jedi-based completion, the default is
                    #       currently still part of the name.
                    append((Signature, f"={p.default}"))

                append((Signature + ".operator", ", "))  ### PATCHED HERE

            if sig.parameters:
                # Pop last comma
                result.pop()

            append((Signature + ".operator", ")"))  ### PATCHED HERE
            append((Signature, " "))
        return result

    return ConditionalContainer(
        content=Window(
            FormattedTextControl(get_text_fragments), height=Dimension.exact(1)
        ),
        filter=
        # Show only when there is a signature
        HasSignature(python_input) &
        # Signature needs to be shown.
        ShowSignature(python_input) &
        # And no sidebar is visible.
        ~ShowSidebar(python_input) &
        # Not done yet.
        ~is_done,
    )


import ptpython.layout

ptpython.layout.signature_toolbar = NEWsignature_toolbar
