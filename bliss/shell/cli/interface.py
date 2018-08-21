# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss command line interface"""

import gevent

from ptpython.python_input import PythonCommandLineInterface

__all__ = ("BlissCommandLineInterface",)


class BlissCommandLineInterface(PythonCommandLineInterface):
    """A python command line interface with a refresh loop"""

    def __init__(self, *args, **kwargs):
        self._refresh_interval = kwargs.pop("refresh_interval", None)
        self.python_input = kwargs["python_input"]
        self.python_input.show_signature = True
        super(BlissCommandLineInterface, self).__init__(*args, **kwargs)
        self._refresh_task = None
        if self._refresh_interval:
            self.on_start += self._start_refresh_loop
            self.on_stop += self._stop_refresh_loop

    @staticmethod
    def _start_refresh_loop(cli):
        cli._refresh_task = gevent.spawn(cli._refresh)

    @staticmethod
    def _stop_refresh_loop(cli):
        if cli._refresh_task:
            cli._refresh_task.kill()

    def _refresh(self):
        while self._refresh_interval:
            self.invalidate()
            gevent.sleep(self._refresh_interval)
