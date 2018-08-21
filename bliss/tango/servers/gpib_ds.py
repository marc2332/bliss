# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
GPIB Tango device server bridge to GPIB.

It uses the Salsa GPIB connection.

Consider using it if you need to connnect to Spec for example.
It is a little bit of an overkill to use this. Most of the times you can use
the direct Gpib class from Salsa directly.

"""
from __future__ import absolute_import

from tango.server import Device, attribute, command, device_property

from bliss.comm.gpib import Gpib as _Gpib


class Gpib(Device):

    url = device_property(
        dtype=str,
        doc="* `enet://<host>:<port>` for NI ENET adapter\n"
        "* `prologix://<host>:<port>` for prologix adapter",
    )
    pad = device_property(dtype=int, default_value=0, doc="primary address")
    sad = device_property(dtype=int, default_value=0, doc="secondary address")
    timeout = device_property(dtype=float, default_value=1., doc="socket timeout")
    tmo = device_property(dtype=int, default_value=13, doc="gpib time limit")
    eot = device_property(dtype=int, default_value=1)
    eos = device_property(dtype=str, default_value="\n")

    def __init__(self, *args, **kwargs):
        self.gpib = None
        Device.__init__(self, *args, **kwargs)

    def delete_device(self):
        if self.gpib:
            self.gpib.close()

    def init_device(self):
        Device.init_device(self)
        kwargs = dict(
            url=self.url, pad=self.pad, sad=self.sad, timeout=self.timeout, tmo=self.tmo
        )
        self.gpib = _Gpib(**kwargs)
        self.gpib.open()

    @property
    def _raw_handler(self):
        return self.gpib._raw_handler

    @command
    def open(self):
        self.gpib.open()

    @command
    def close(self):
        self.gpib.close()

    @command(dtype_in="int32", dtype_out=str)
    def read(self, size):
        return self.gpib.read(size=size)

    @command(dtype_in=str)
    def write(self, msg):
        self.gpib.write(msg)

    @command(dtype_in=[str], dtype_out=str, doc_in="(msg, size)")
    def write_read(self, msg_and_size):
        msg, size = msg_and_size
        return self.gpib.write_read(msg, size=int(size))

    @command(dtype_in=str, dtype_out=str)
    def write_readline(self, msg):
        return self.gpib.write_readline(msg)

    @command(dtype_in=[str], dtype_out=[str], doc_in="(msg, nb_lines)")
    def write_readlines(self, msg_and_nb_lines):
        msg, nb_lines = msg_and_nb_lines
        return self.gpib.write_readlines(msg, int(nb_lines))

    @command
    def flush(self):
        self.gpib.flush()

    # --- 'low level' commands: to be used by the TangoGpib class in Salsa  ---

    @command(dtype_in=int)
    def ibtmo(self, timeout):
        self._raw_handler.ibtmo(timeout)

    @command(dtype_in=int, dtype_out=str)
    def ibrd(self, size):
        return self._raw_handler.ibrd(size)

    @command(dtype_in=str)
    def ibwrt(self, msg):
        self._raw_handler.ibwrt(msg)


def main():
    from tango import GreenMode
    from tango.server import run

    run([Gpib], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
