# -*- coding: utf-8 -*-

"""
TANGO Bliss device client

Example::

    from bliss.tango.clients.bliss import Bliss

    bliss = Bliss("ID00/bliss/sixc")

    bliss.run('ascan(th, 0, 180, 100, 0.1')
"""

import sys
import functools
import gevent
from bliss.common.tango import DeviceProxy


def output(stream, msg):
    if not msg or not stream:
        return
    stream.write(msg)
    stream.flush()


class Bliss(object):

    LOOP_TIME = 1 / 25.  # 25x per second

    def __init__(self, dev_name, out_stream=sys.stdout, err_stream=sys.stderr):
        self.__dev = DeviceProxy(dev_name)
        self.__out_stream = out_stream
        self.__err_stream = err_stream
        self.__curr_cmd = None

        for cmd in ("execute", "is_running", "stop", "init"):
            setattr(self, cmd, functools.partial(self.__dev.command_inout, cmd))

    def output(self, msg):
        output(self.__out_stream, msg)

    def error(self, msg):
        if not msg:
            return
        msg = "\033[31m" + msg + "\033[39m"
        output(self.__err_stream, msg)

    def update_output(self):
        self.output(self.__dev.output_channel)
        self.error(self.__dev.error_channel)

    def update_input(self):
        if self.__dev.need_input:
            self.__dev.input_channel = raw_input()

    def __run(self, cmd):
        self.__curr_cmd = self.execute(cmd)
        while self.is_running(self.__curr_cmd):
            self.update_output()
            self.update_input()
            gevent.sleep(self.LOOP_TIME)
        # final output read in case there is still something
        self.update_output()
        self.__curr_cmd = None

    def run(self, cmd):
        if self.__curr_cmd:
            raise RuntimeError("Old command is still executing")
        try:
            self.__run(cmd)
        except KeyboardInterrupt:
            cmd_id = self.__curr_cmd
            if cmd_id:
                self.stop(cmd_id)
            self.update_output()
        finally:
            self.__curr_cmd = None

    def resetup(self):
        self.init()
