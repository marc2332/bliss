#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
#
# Patch to modify the behavior of the ptpython signature_toolbar
# The code for def signature_toolbar corresponds to ptpython version 2.0.4

from prompt_toolkit.application import get_app

from prompt_toolkit.filters import is_done, renderer_height_is_known, Condition
from prompt_toolkit.layout.containers import Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from ptpython.utils import if_mousedown
from ptpython.layout import get_inputmode_fragments


def NEWstatus_bar(python_input):
    """
    Create the `Layout` for the status bar.
    """
    TB = "class:status-toolbar"

    @if_mousedown
    def toggle_paste_mode(mouse_event):
        python_input.paste_mode = not python_input.paste_mode

    @if_mousedown
    def enter_history(mouse_event):
        python_input.enter_history()

    def get_text_fragments():
        python_buffer = python_input.default_buffer

        result = []
        append = result.append

        append((TB, " "))
        result.extend(get_inputmode_fragments(python_input))
        append((TB, " "))

        # Position in history.
        append(
            (
                TB,
                "%i/%i "
                % (python_buffer.working_index + 1, len(python_buffer._working_lines)),
            )
        )

        # Shortcuts.
        app = get_app()
        if (
            not python_input.vi_mode
            and app.current_buffer == python_input.search_buffer
        ):
            append((TB, "[Ctrl-G] Cancel search [Enter] Go to this position."))
        elif bool(app.current_buffer.selection_state) and not python_input.vi_mode:
            # Emacs cut/copy keys.
            append((TB, "[Ctrl-W] Cut [Meta-W] Copy [Ctrl-Y] Paste [Ctrl-G] Cancel"))
        else:
            result.extend(
                [
                    (TB + " class:key", "[F3]", enter_history),
                    (TB, " History ", enter_history),
                    (TB, "[F5] Scans "),
                    (TB + " class:key", "[F6]", toggle_paste_mode),
                    (TB, " ", toggle_paste_mode),
                ]
            )

            if python_input.paste_mode:
                append(
                    (TB + " class:paste-mode-on", "Paste mode (on)", toggle_paste_mode)
                )
            else:
                append((TB, "Paste mode", toggle_paste_mode))

        return result

    return ConditionalContainer(
        content=Window(content=FormattedTextControl(get_text_fragments), style=TB),
        filter=~is_done
        & renderer_height_is_known
        & Condition(
            lambda: python_input.show_status_bar
            and not python_input.show_exit_confirmation
        ),
    )


import ptpython.layout

ptpython.layout.status_bar = NEWstatus_bar
