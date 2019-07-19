# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import contextlib
import functools
import gevent
import traceback
from prompt_toolkit.application import Application
from prompt_toolkit.shortcuts.progress_bar import base
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import (
    Layout,
    Window,
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    VSplit,
)
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.dimension import D
from bliss.common.greenlet_utils import KillMask


@contextlib.contextmanager
def _auto_refresh_context(app, refresh_interval):
    " Return a context manager for the auto-refresh loop. "

    def run():
        while True:
            gevent.sleep(refresh_interval)
            with KillMask():
                app.invalidate()

    t = gevent.spawn(run)
    try:
        yield
    finally:
        t.kill()


class _ProgressControl(base._ProgressControl):
    def __init__(self, current_task, progress_bar, formatter):
        self.progress_bar = progress_bar
        self.formatter = formatter
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            gevent.kill(current_task, KeyboardInterrupt)

        self._key_bindings = kb


class ProgressBar(base.ProgressBar):
    def __enter__(self):
        """
        Same behavior as prompt_toolkit progressbar
        except that it's gevent base instead of thread.
        Code is copied and pasted with thread replace with gevent.task
        """
        current_task = gevent.getcurrent()
        # Create UI Application.
        title_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: self.title),
                height=1,
                style="class:progressbar,title",
            ),
            filter=Condition(lambda: self.title is not None),
        )

        @Condition
        def is_done():
            return self.app.is_done

        @Condition
        def renderer_height_is_known():
            return self.app.renderer.height_is_known

        bottom_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: self.bottom_toolbar, style="class:bottom-toolbar.text"
                ),
                style="class:bottom-toolbar",
                height=1,
            ),
            filter=~is_done
            & renderer_height_is_known
            & Condition(lambda: self.bottom_toolbar is not None),
        )

        def width_for_formatter(formatter):
            # Needs to be passed as callable (partial) to the 'width'
            # parameter, because we want to call it on every resize.
            return formatter.get_width(progress_bar=self)

        progress_controls = [
            Window(
                content=_ProgressControl(current_task, self, f),
                width=functools.partial(width_for_formatter, f),
            )
            for f in self.formatters
        ]

        self.app = Application(
            min_redraw_interval=.05,
            layout=Layout(
                HSplit(
                    [
                        title_toolbar,
                        VSplit(
                            progress_controls,
                            height=lambda: D(
                                preferred=len(self.counters), max=len(self.counters)
                            ),
                        ),
                        Window(),
                        bottom_toolbar,
                    ]
                )
            ),
            style=self.style,
            key_bindings=self.key_bindings,
            color_depth=self.color_depth,
            output=self.output,
            input=self.input,
        )

        # Run application in different thread.
        def run():
            with _auto_refresh_context(self.app, .3):
                try:
                    self.app.run()
                except BaseException as e:
                    traceback.print_exc()
                    print(e)

        self._thread = gevent.spawn(run)

        return self
