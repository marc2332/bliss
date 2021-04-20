# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Module providing dialogs to interact with the user """

import functools
import subprocess
import gevent
import threading
import asyncio
import os

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app

# from prompt_toolkit.eventloop import run_in_executor
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout import containers
from prompt_toolkit.layout.containers import HSplit, VSplit
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.widgets import (
    ProgressBar,
    Dialog,
    Button,
    Label,
    Box,
    TextArea,
    Frame,
)

from prompt_toolkit.mouse_events import MouseEventType

from prompt_toolkit.layout.containers import Float, FloatContainer, ConditionalContainer
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.filters import Condition, has_completions
from prompt_toolkit.styles import Style

from prompt_toolkit.completion import PathCompleter, WordCompleter

from prompt_toolkit.widgets import Checkbox as Checkbox_Orig
from prompt_toolkit.widgets import RadioList  # as RadioList_Orig


__all__ = [
    "yes_no_dialog",
    "button_dialog",
    "input_dialog",
    "message_dialog",
    "radiolist_dialog",
    "BlissDialog",
]


# ==== ESRF COLORS AND DEFAULT PROMPT TOOLKIT DIALOG COLORS ======

_ESRF_STYLE = Style.from_dict(
    {
        "warning-msg": "bg:#ec7404 #ffffff",  # ec7404 #aa0000
        "error_state": "bg:#ec7404 #ffffff",  # ec7404 #aa0000
        "dialog frame.label": "#ad007c bold",
        "dialog": "bg:#132577",
        "dialog.body text-area": "bg:#cfd1d2",
        "button.focused": "bg:#ad007c #ffffff",
        "helper": "bg:#ad007c #ffffff bold ",
    }
)


if 0:
    # ==== ESRF COLORS ======
    # PANTONE BLEU 2747C             = #132577

    # PANTONE COOL GRAY 1C (light)   = #f4f4f4
    # PANTONE COOL GRAY 4C (medium)  = #cfd1d2
    # PANTONE COOL GRAY 7C (darker)  = #b1b3b4

    # PANTONE 166C (orange 1)        = #ec7404
    # PANTONE 138C (orange 2)        = #f6a400
    # PANTONE 109C (yellow)          = #ffdd00
    # PANTONE 362C (green)           = #509f25
    # PANTONE 299C (light blue)      = #0097d3
    # PANTONE 2405C (purple)         = #ad007c

    # === DEFAULTPROMPT TOOLKIT DIALOG COLORS ===
    """ 
    WIDGETS_STYLE = [
        # Dialog windows.
        ('dialog',                                  'bg:#4444ff'),
        ('dialog.body',                             'bg:#ffffff #000000'),
        ('dialog.body text-area',                    'bg:#cccccc'),
        ('dialog.body text-area last-line',          'underline'),

        ('dialog frame.label',                      '#ff0000 bold'),

        # Scrollbars in dialogs.
        ('dialog.body scrollbar.background',        ''),
        ('dialog.body scrollbar.button',            'bg:#000000'),
        ('dialog.body scrollbar.arrow',             ''),
        ('dialog.body scrollbar.start',             'nounderline'),
        ('dialog.body scrollbar.end',               'nounderline'),

        # Buttons.
        ('button',                                  ''),
        ('button.arrow',                            'bold'),
        ('button.focused',                          'bg:#aa0000 #ffffff'),

        # Menu bars.
        ('menu-bar',                                'bg:#aaaaaa #000000'),
        ('menu-bar.selected-item',                  'bg:#ffffff #000000'),
        ('menu',                                    'bg:#888888 #ffffff'),
        ('menu.border',                             '#aaaaaa'),
        ('menu.border shadow',                      '#444444'),

        # Shadows.
        ('dialog shadow',                           'bg:#000088'),
        ('dialog.body shadow',                      'bg:#aaaaaa'),

        ('progress-bar',                             'bg:#000088'),
        ('progress-bar.used',                        'bg:#ff0000'),
    ]
    """


# ===================== PROMPT TOOLKIT PATCHING ==================

# Modify prompt_toolkit Checkbox obj
# Add a mouse handler to check ON or OFF the checkbox
class Checkbox(Checkbox_Orig):
    def _get_text_fragments(self):
        def mouse_handler(mouse_event):

            if mouse_event.event_type == MouseEventType.MOUSE_UP:
                self.checked = not self.checked

        result = super()._get_text_fragments()

        # Add mouse handler to all fragments.
        for i in range(len(result)):
            result[i] = (result[i][0], result[i][1], mouse_handler)

        return result


# ================================================================


def _run_dialog(dialog, style, extra_bindings=None, full_screen=True):
    " Turn the `Dialog` into an `Application` and run it. "
    application = _create_app(dialog, style, extra_bindings, full_screen)
    res = None

    def in_thread():
        nonlocal res
        res = asyncio.run(application.run_async())

    thread = threading.Thread(target=in_thread)
    thread.start()
    thread.join()

    return res


def _create_app(dialog, style, extra_bindings=None, full_screen=True):
    # Key bindings.
    kb = load_key_bindings()
    merged_bindings = [kb]
    if extra_bindings is not None:
        merged_bindings.append(extra_bindings)

    return Application(
        layout=Layout(dialog),
        key_bindings=merge_key_bindings(merged_bindings),
        mouse_support=True,
        style=style,
        full_screen=full_screen,
    )


def _return_none():
    " Button handler that returns None. "
    get_app().exit()


# ==== BASIC DIALOGS =====================================================================


def yes_no_dialog(
    title="", text="", yes_text="Yes", no_text="No", style=None, full_screen=True
):
    """
    Display a Yes/No dialog.
    Return a boolean.
    """

    def yes_handler():
        get_app().exit(result=True)

    def no_handler():
        get_app().exit(result=False)

    dialog = Dialog(
        title=title,
        body=Label(text=text, dont_extend_height=True),
        buttons=[
            Button(text=yes_text, handler=yes_handler),
            Button(text=no_text, handler=no_handler),
        ],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


def button_dialog(title="", text="", buttons=[], style=None, full_screen=True):
    """
    Display a dialog with button choices (given as a list of tuples).
    Return the value associated with button.
    """

    def button_handler(v):
        get_app().exit(result=v)

    dialog = Dialog(
        title=title,
        body=Label(text=text, dont_extend_height=True),
        buttons=[
            Button(text=t, handler=functools.partial(button_handler, v))
            for t, v in buttons
        ],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


def input_dialog(
    title="",
    text="",
    ok_text="OK",
    cancel_text="Cancel",
    completer=None,
    password=False,
    style=None,
    full_screen=True,
):
    """
    Display a text input box.
    Return the given text, or None when cancelled.
    """

    def accept(buf):
        get_app().layout.focus(ok_button)
        return True  # Keep text.

    def ok_handler():
        get_app().exit(result=textfield.text)

    ok_button = Button(text=ok_text, handler=ok_handler)
    cancel_button = Button(text=cancel_text, handler=_return_none)

    textfield = TextArea(
        multiline=False,
        focus_on_click=True,
        password=password,
        completer=completer,
        accept_handler=accept,
    )

    dialog = Dialog(
        title=title,
        body=HSplit(
            [Label(text=text, dont_extend_height=True), textfield],
            padding=D(preferred=1, max=1),
        ),
        buttons=[ok_button, cancel_button],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


def message_dialog(title="", text="", ok_text="Ok", style=None, full_screen=True):
    """
    Display a simple message box and wait until the user presses enter.
    """
    dialog = Dialog(
        title=title,
        body=Label(text=text, dont_extend_height=True),
        buttons=[Button(text=ok_text, handler=_return_none)],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


def radiolist_dialog(
    title="",
    text="",
    ok_text="Ok",
    cancel_text="Cancel",
    values=None,
    style=None,
    full_screen=True,
):
    """
    Display a simple list of element the user can choose amongst.

    Only one element can be selected at a time using Arrow keys and Enter.
    The focus can be moved between the list and the Ok/Cancel button with tab.
    """

    def ok_handler():
        get_app().exit(result=radio_list.current_value)

    radio_list = RadioList(values)

    dialog = Dialog(
        title=title,
        body=HSplit([Label(text=text, dont_extend_height=True), radio_list], padding=1),
        buttons=[
            Button(text=ok_text, handler=ok_handler),
            Button(text=cancel_text, handler=_return_none),
        ],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


def checkbox_dialog(
    title="", text="", ok_text="Ok", cancel_text="Cancel", style=None, full_screen=True
):
    """
    Display a checkbox.
    """

    def ok_handler():
        get_app().exit(result=cb.checked)

    cb = Checkbox(text)
    body = cb

    dialog = Dialog(
        title=title,
        body=body,
        buttons=[
            Button(text=ok_text, handler=ok_handler),
            Button(text=cancel_text, handler=_return_none),
        ],
        with_background=True,
    )

    return _run_dialog(dialog, style, full_screen=full_screen)


# ===========================================================================================


def display(user_dlg, title="", full_screen=True):
    """ display a single widget in a dialog application """

    dlg = None

    if user_dlg.label is None:
        text = ""
    else:
        text = user_dlg.label

    values = user_dlg.values

    if user_dlg.wtype == "msg":
        dlg = message_dialog(
            title, text, ok_text="Ok", style=_ESRF_STYLE, full_screen=full_screen
        )

    elif user_dlg.wtype == "yesno":
        dlg = yes_no_dialog(
            title,
            text,
            yes_text="Yes",
            no_text="No",
            style=_ESRF_STYLE,
            full_screen=full_screen,
        )

    elif user_dlg.wtype in ["input", "file_input"]:

        if user_dlg.wtype == "file_input":
            if user_dlg.completer is None:
                completer = PathCompleter()
            else:
                completer = WordCompleter(user_dlg.completer, ignore_case=True)

        elif user_dlg.completer is not None:
            completer = WordCompleter(user_dlg.completer, ignore_case=True)

        else:
            completer = None

        dlg = input_dialog(
            title,
            text,
            ok_text="OK",
            cancel_text="Cancel",
            completer=completer,
            password=False,
            style=_ESRF_STYLE,
            full_screen=full_screen,
        )

    elif user_dlg.wtype == "choice":
        dlg = radiolist_dialog(
            title,
            text,
            ok_text="Ok",
            cancel_text="Cancel",
            values=values,
            style=_ESRF_STYLE,
            full_screen=full_screen,
        )

    elif user_dlg.wtype == "checkbox":
        dlg = checkbox_dialog(
            title,
            text,
            ok_text="Ok",
            cancel_text="Cancel",
            style=_ESRF_STYLE,
            full_screen=full_screen,
        )

    return dlg


class DlgWidget:
    """ Dialog widget base class """

    def __init__(self, user_dlg, boss=None):
        self.dlg = user_dlg
        self.boss = boss
        self.wdata = None
        self.body = None
        self.error_state = False
        self.build()

    def build(self):

        body = None

        if self.dlg.wtype == "msg":
            body = Label(
                text=self.dlg.label,
                dont_extend_height=True,
                dont_extend_width=not self.dlg.text_expand,
            )

            if self.dlg.text_align is not None:
                body.window.align = self.dlg.text_align

        elif self.dlg.wtype in ["input", "file_input"]:

            sub_body = []

            if self.dlg.label is not None:
                msg = self.dlg.label
                if self.dlg.label not in ["", " "]:
                    msg += " "

                wlabel = Label(
                    text=msg,
                    dont_extend_height=True,
                    dont_extend_width=not self.dlg.text_expand,
                )

                if self.dlg.text_align is not None:
                    wlabel.window.align = self.dlg.text_align

                sub_body.append(wlabel)

            if self.dlg.wtype == "file_input":
                if self.dlg.completer is None:
                    completer = PathCompleter()
                else:
                    completer = WordCompleter(self.dlg.completer, ignore_case=True)

            elif self.dlg.completer is not None:
                completer = WordCompleter(self.dlg.completer, ignore_case=True)

            else:
                completer = None

            def get_style():
                if self.error_state:
                    return "class:error_state"
                else:
                    return "class:text-area"

            self.wdata = TextArea(
                multiline=False,
                focus_on_click=True,
                # password=password,
                completer=completer,
                complete_while_typing=True,
                accept_handler=self.accept,
            )

            self.wdata.window.style = get_style

            # set inital text
            self.wdata.text = str(self.dlg.defval)
            # and set cursor to end of line
            buff = self.wdata.buffer
            pos = buff.document.get_end_of_line_position()
            buff._set_cursor_position(buff.cursor_position + pos)

            # === BINDINGS ==================================================
            def comp_next(event):
                " Initialize autocompletion, or select the next completion. "
                buff = get_app().current_buffer
                if buff.complete_state:
                    buff.complete_next()
                else:
                    buff.start_completion(select_first=False)

            def comp_prev(event):
                " Initialize autocompletion, or select the next completion. "
                buff = get_app().current_buffer
                if buff.complete_state:
                    buff.complete_previous()
                else:
                    buff.start_completion(select_first=False)

            kb = KeyBindings()
            kb.add("c-space")(comp_next)
            kb.add("up")(comp_prev)
            kb.add("down")(comp_next)

            # === ENABLE VALIDATOR CHECK WHEN LIVING A TEXT AREA FIELD ===

            def focus_next_wdg(event):
                if self.check_input(self.get_result()):
                    get_app().layout.focus_next()
                    # buff = get_app().current_buffer
                    # pos = buff.document.get_end_of_line_position()
                    # buff._set_cursor_position(buff.cursor_position + pos)

            def focus_previous_wdg(event):
                if self.check_input(self.get_result()):
                    get_app().layout.focus_previous()
                    # buff = get_app().current_buffer
                    # pos = buff.document.get_end_of_line_position()
                    # buff._set_cursor_position(buff.cursor_position + pos)

            kb.add("tab")(focus_next_wdg)
            kb.add("s-tab")(focus_previous_wdg)

            # === MAKE BODY LIST =========================================
            sub_body.append(self.wdata)
            body = VSplit(sub_body, key_bindings=kb)

        elif self.dlg.wtype == "choice":
            sub_body = []
            if self.dlg.label is not None:
                wlabel = Label(
                    text=self.dlg.label + " ",
                    dont_extend_height=True,
                    dont_extend_width=not self.dlg.text_expand,
                )

                if self.dlg.text_align is not None:
                    wlabel.window.align = self.dlg.text_align

                sub_body.append(wlabel)

            self.wdata = RadioList(self.dlg.values)

            if self.dlg.defval >= 0 and self.dlg.defval < len(self.dlg.values):

                self.wdata.current_value = self.dlg.values[self.dlg.defval][0]
                self.wdata._selected_index = self.dlg.defval

            sub_body.append(self.wdata)
            body = HSplit(sub_body)

        elif self.dlg.wtype == "checkbox":
            self.wdata = Checkbox(self.dlg.label)

            try:
                self.wdata.checked = bool(self.dlg.defval)
            except Exception:
                pass

            body = self.wdata

        else:
            raise NotImplementedError

        self.body = body

    def check_input(self, str_input):
        if self.dlg.validator:
            try:
                self.dlg.validator.check(str_input)
                self.error_state = False

                try:
                    self.boss.clear_error(self)
                except Exception:
                    pass

                return True

            except Exception as e:
                self.error_state = True

                try:
                    msg = f"!!! {type(e).__name__}: {e} !!!"  # {self.dlg.label}
                    self.boss.set_error(msg, self)
                except Exception:
                    pass

                return False

        else:
            # self.error_state = False
            return True

    def accept(self, buf):
        """ Called while pressing enter in a TextArea field """
        if self.check_input(buf.text):
            get_app().layout.focus_next()
        return True

    def get_result(self):
        if self.dlg.wtype == "msg":
            return True

        elif self.dlg.wtype == "yesno":
            raise NotImplementedError

        elif self.dlg.wtype in ["input", "file_input"]:
            return self.wdata.text

        elif self.dlg.wtype == "choice":
            return self.wdata.current_value

        elif self.dlg.wtype == "checkbox":
            return self.wdata.checked


class BlissDialog(Dialog):
    def __init__(
        self,
        user_dlg_list,
        title="BlissDialog",
        ok_text="OK",
        cancel_text="Cancel",
        style=_ESRF_STYLE,
        paddings=(1, 1),
        show_help=False,
        disable_tmux_mouse=True,
    ):

        self.user_dlg_list = user_dlg_list
        self.style = style
        self.paddings = paddings
        self.show_error = False
        self.show_help = show_help
        self.disable_tmux_mouse = disable_tmux_mouse

        self.flatten_wdlg_list = []

        ok_but = Button(text=ok_text, handler=self.ok_handler)
        cl_but = Button(text=cancel_text, handler=self.cancel_handler)
        buttons = [ok_but, cl_but]

        body = self.build()
        super().__init__(title=title, body=body, buttons=buttons, with_background=True)

        def focus_ok(event):
            get_app().layout.focus(ok_but.window)

        def on_ctrl_c(event):
            self.return_and_close(False)

        self.extra_bindings = KeyBindings()
        self.extra_bindings.add("end")(focus_ok)
        self.extra_bindings.add("c-c")(on_ctrl_c)
        self.extra_bindings.add("down", filter=~has_completions)(focus_next)
        self.extra_bindings.add("up", filter=~has_completions)(focus_previous)

        if self.disable_tmux_mouse and "TMUX" in os.environ:
            try:
                subprocess.run(["tmux", "set-option", "-g", "mouse", "off"])
            except Exception:
                pass

    def return_and_close(self, results=False):
        if self.disable_tmux_mouse and "TMUX" in os.environ:
            try:
                subprocess.run(["tmux", "set-option", "-g", "mouse", "on"])
            except Exception:
                pass

        get_app().exit(result=results)

    def ok_handler(self):
        results = {}

        for wdlg in self.flatten_wdlg_list:
            res = wdlg.get_result()
            if wdlg.check_input(res) is False:
                return

            # cast returned values for Int and Float InputDialogs
            if type(wdlg.dlg).__name__ == "UserIntInput":
                res = int(res)
            elif type(wdlg.dlg).__name__ == "UserFloatInput":
                res = float(res)

            # store the results in a dict
            if wdlg.dlg.name is None:
                results[wdlg.dlg] = res
            else:
                results[wdlg.dlg.name] = res

        # SECOND LOOP, NOW WE ARE SURE THAT ALL VALUES ARE OK
        # WE SET DEFVAL TO RES VALUE
        for wdlg in self.flatten_wdlg_list:
            try:
                wdlg.dlg.defval = results[wdlg.dlg.name]
            except KeyError:
                wdlg.dlg.defval = results[wdlg.dlg]

        # for UserChoice, store the index
        if type(wdlg.dlg).__name__ == "UserChoice":
            wdlg.dlg.defval = [i[0] for i in wdlg.dlg.values].index(wdlg.dlg.defval)

        self.return_and_close(results)

    def cancel_handler(self):
        self.return_and_close(False)

    def set_error(self, msg, wdlg):
        self.error_label.text = msg
        self.show_error = True
        wdlg.error_state = True

    def clear_error(self, wdlg):
        self.error_label.text = ""
        self.show_error = False
        wdlg.error_state = False

    def _get_zbody(self, dlg):
        if dlg.wtype == "container":
            z_list = []
            for subdlg in dlg.dlgs:
                subbody = self._get_zbody(subdlg)
                z_list.append(subbody)

            if dlg.splitting == "h":
                zbody = HSplit(z_list, padding=dlg.padding)
            else:
                zbody = VSplit(z_list, padding=dlg.padding)

            if dlg.border:
                zbody = Box(zbody, padding=dlg.border)

            if dlg.title is not None:
                zbody = Frame(zbody, dlg.title)

        else:
            dlg_widget = DlgWidget(dlg, boss=self)
            zbody = dlg_widget.body
            self.flatten_wdlg_list.append(dlg_widget)

        return zbody

    def build(self):
        y_list = []

        # === Add bindings helper ====
        if self.show_help:
            bh = Label(
                text=" >>> Next/Prev: tab/s-tab | Completion: up/down | Validate: enter | OK: end | Cancel: c-c <<< ",
                dont_extend_height=True,
                dont_extend_width=True,
                style="class:helper",
            )
            bh.window.align = "JUSTIFY"

            y_list.append(bh)

        for user_dlgs in self.user_dlg_list:

            x_list = []
            for user_dlg in user_dlgs:

                # introspect container of containers
                zbody = self._get_zbody(user_dlg)
                x_list.append(zbody)

            xbody = VSplit(x_list, padding=self.paddings[1])
            y_list.append(xbody)

        self.error_label = Label(
            text="Error",
            dont_extend_height=True,
            dont_extend_width=True,
            style="class:warning-msg",
        )

        self.error_label.window.align = "JUSTIFY"

        cc = ConditionalContainer(
            content=self.error_label, filter=Condition(lambda: self.show_error)
        )

        y_list.append(cc)

        body = HSplit(y_list, padding=self.paddings[0])

        fbody = FloatContainer(
            content=body,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=16, scroll_offset=1),
                )
            ],
        )

        return fbody

    def show(self, full_screen=True):
        gevent.spawn(self.after_launch, 0.1)

        ans = _run_dialog(
            self,
            self.style,
            extra_bindings=self.extra_bindings,
            full_screen=full_screen,
        )

        return ans

    def after_launch(self, delay=0.1):
        gevent.sleep(delay)
        get_app().layout.focus_next()
        get_app().layout.focus_last()


def select_dialog(dialog_classes, title: str = None):
    """
    Display a dialog with button choices (given as a list of tuples).
    Return the value associated with button.

    Returns:
        The selected dialog class else None if the dialog was cancelled.
    """
    if title is None:
        title = "Select dialog"

    def button_handler(dialog_class, foo=None):
        get_app().exit(result=dialog_class)

    key_bindings = KeyBindings()

    rows = []
    max_size = max([len(str(d)) for d in dialog_classes])
    for num, dialog_class in enumerate(dialog_classes):
        on_click = functools.partial(button_handler, dialog_class)

        label_button = str(dialog_class).capitalize()
        if num <= 8:
            key_bindings.add(f"{num+1}")(on_click)
            label = f"{num + 1}."
        else:
            label = "#."

        button = Button(
            text=label_button, handler=on_click, width=len(label_button) + 4
        )

        num_label = Label(label)
        empty = containers.Window(
            style="class:frame.border", width=max_size - len(label_button), height=1
        )
        row = VSplit([num_label, button, empty], align=containers.HorizontalAlign.LEFT)
        rows.append(row)

    body = HSplit(rows, key_bindings=key_bindings)

    cancel = Button(text="Cancel", handler=functools.partial(button_handler, None))
    body = Box(body)

    dialog = Dialog(title=title, body=body, buttons=[cancel], with_background=True)
    return _run_dialog(dialog, style=_ESRF_STYLE)
