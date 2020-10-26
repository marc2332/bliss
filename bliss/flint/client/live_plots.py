# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides plot helper class to deal with flint proxy.
"""

import gevent
import time

from . import utils
from . import plots
from . import proxy


class LiveImagePlot:
    """ Use Flint to display Images (Live and snapshot) """

    def __init__(self, get_data_cb=None, name="LiveImagePlot"):
        """ get_data_cb (optional) is a callable returning an image (2D numpy array)  """

        if get_data_cb is None:
            self._get_data_cb = None
        else:
            self._get_data_cb = get_data_cb

        self._name = name

        self._task = None
        self._stop_event = gevent.event.Event()
        self._sleep_time = 0.1
        self._check_flint_poll_time = 2.0

        self.fig = None

    def __del__(self):
        self.stop()

    @property
    def fps(self):
        return 1. / self._sleep_time

    @fps.setter
    def fps(self, fps):
        self._sleep_time = 1. / fps

    @property
    def data_cb(self):
        return self._get_data_cb

    @data_cb.setter
    def data_cb(self, cb):
        """ Stores a callable that returns the 2D data. 
            It will be called by the Live plot to refresh the image data
        """

        if not callable(cb):
            raise ValueError(f"{cb} is not a callable!")
        self._get_data_cb = cb

    def create_plot(self, data):
        flint = proxy.get_flint()
        self.fig = flint.add_plot(
            plots.ImagePlot, name=self._name, selected=True, closeable=True
        )
        self.fig.plot(data=data)

    def is_plot_active(self):
        return self.fig is not None and self.fig.is_open()

    def start(self):
        """ Start a Live display in Flint, calling 'self.data_cb' to refresh the image data """

        if self._get_data_cb is None:
            raise ValueError("self._get_data_cb is None!")

        if not self.is_plot_active():
            self.create_plot(self._get_data_cb())

        if not self._task:
            self._stop_event.clear()
            self._task = gevent.spawn(self._run)

    def stop(self):
        if self._task is not None:
            self._stop_event.set()
            with gevent.Timeout(2.0):
                self._task.join()

    def plot(self, data):
        """ Display 'data' as an image in Flint """

        if not self.is_plot_active():
            self.create_plot(data)
        else:
            self._plot(data)

    def _plot(self, data):
        with utils.draw_manager(self.fig):
            self.fig.add_data(data, field="img")
            self.fig.select_data("img")

    def _run(self):

        t0 = time.time()
        while not self._stop_event.is_set():

            try:
                data = self._get_data_cb()
                self._plot(data)

                # check that the plot is still open in Flint
                if time.time() - t0 > self._check_flint_poll_time:
                    t0 = time.time()
                    if not self.is_plot_active():
                        break

            except Exception as _e:
                break

            gevent.sleep(self._sleep_time)
