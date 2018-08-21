# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common.task import task
from bliss.common.measurement import SamplingCounter
from bliss.common.greenlet_utils import protect_from_kill
from gevent.lock import Semaphore
import time
import gevent
import socket


class LSCounter(SamplingCounter):
    def __init__(self, name, controller, channel):
        SamplingCounter.__init__(self, controller.name + "." + name, controller)
        self.__controller = controller
        self.__channel = channel

    @property
    def channel(self):
        return self.__channel

    def read(self):
        return float(self.__controller._putget("krdg? %s" % self.channel))


class ls335(object):
    def __init__(self, name, config):
        self.name = name

        self.gpib_controller_host = config.get("gpib_controller_host")
        self.gpib_address = config.get("gpib_address")

        self.__lock = Semaphore()
        self.__control = None

    def __connect(self):
        self.__control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__control.connect((self.gpib_controller_host, 1234))
        self.__control.sendall(
            "++mode 1\r\n++addr %d\r\n++auto 0\r\nmode 0\r\n" % self.gpib_address
        )
        return self._putget("*idn?").startswith("LS")

    @protect_from_kill
    def _putget(self, cmd):
        with self.__lock:
            if self.__control is None:
                self.__connect()
            self.__control.sendall("%s\r\n++read eoi\r\n" % cmd)
            return self.__control.recv(1024)

    @property
    def A(self):
        return LSCounter("A", self, "a")

    @property
    def B(self):
        return LSCounter("B", self, "b")
