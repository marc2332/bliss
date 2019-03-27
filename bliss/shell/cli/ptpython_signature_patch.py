#
# This file is part of the bliss project
#
# Copyright (c) 2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
#
# Patch to modify the behavior of the ptpython signature_toolbar
# The code for def signature_toolbar corresponds to ptpython version 2.0.4

from prompt_toolkit.layout.containers import Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from ptpython.filters import HasSignature, ShowSignature
from prompt_toolkit.filters import is_done, has_completions
from ptpython.layout import show_completions_menu, show_multi_column_completions_menu


def NEWsignature_toolbar(python_input):
    """
    Return the `Layout` for the signature.
    """

    def get_text_fragments():
        result = []
        append = result.append
        Signature = "class:signature-toolbar"

        if python_input.signatures:
            sig = python_input.signatures[0]  # Always take the first one.

            append((Signature, " "))
            try:
                append(
                    (Signature, sig.full_name.split(".")[-1])
                )  ### HERE IS THE BLISS PATCH
            except IndexError:
                # Workaround for #37: https://github.com/jonathanslenders/python-prompt-toolkit/issues/37
                # See also: https://github.com/davidhalter/jedi/issues/490
                return []

            append((Signature + ",operator", "("))

            try:
                enumerated_params = enumerate(sig.params)
            except AttributeError:
                # Workaround for #136: https://github.com/jonathanslenders/ptpython/issues/136
                # AttributeError: 'Lambda' object has no attribute 'get_subscope_by_name'
                return []

            for i, p in enumerated_params:
                # Workaround for #47: 'p' is None when we hit the '*' in the signature.
                #                     and sig has no 'index' attribute.
                # See: https://github.com/jonathanslenders/ptpython/issues/47
                #      https://github.com/davidhalter/jedi/issues/598
                description = p.description if p else "*"  # or '*'
                sig_index = getattr(sig, "index", 0)

                if i == sig_index:
                    # Note: we use `_Param.description` instead of
                    #       `_Param.name`, that way we also get the '*' before args.
                    append((Signature + ",current-name", str(description)))
                else:
                    append((Signature, str(description)))
                append((Signature + ",operator", ", "))

            if sig.params:
                # Pop last comma
                result.pop()

            append((Signature + ",operator", ")"))
            append((Signature, " "))
        return result

    return ConditionalContainer(
        content=Window(
            FormattedTextControl(get_text_fragments), height=Dimension.exact(1)
        ),
        filter=
        # Show only when there is a signature
        HasSignature(python_input) &
        # And there are no completions to be shown. (would cover signature pop-up.)
        ~(
            has_completions
            & (
                show_completions_menu(python_input)
                | show_multi_column_completions_menu(python_input)
            )
        )
        # Signature needs to be shown.
        & ShowSignature(python_input) &
        # Not done yet.
        ~is_done,
    )


import ptpython.layout

ptpython.layout.signature_toolbar = NEWsignature_toolbar
