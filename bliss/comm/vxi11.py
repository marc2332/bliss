# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.comm.vxi11_base import Instrument


class Vxi11:
    def __init__(
        self,
        host=None,
        eol=b"\n",  # end of line for each rx message
        timeout=5.,  # default timeout for read write
        name=None,
    ):

        self._instrument = Instrument(
            host, name=name, client_id=None, term_char=None
        )  # term_char != eol !!!
        self._instrument.timeout = timeout
        self._eol = eol

    def connect(self, host=None, port=None, timeout=None):
        raise NotImplementedError("still to come...")

    def __close__(self):
        return self.close()

    def close(self):
        self._instrument.close()

    def raw_read(self, maxsize=-1, timeout=None):
        # signature from bliss socket
        # timeout so far ignored
        return self._instrument.read_raw(num=maxsize)

    #   def raw_write(self, maxsize=None, timeout=None):
    #       raise NotImplementedError("still to come...")

    def read(self, size=1, timeout=None):
        # signature from bliss socket
        # timeout so far ignored
        return self._instrument.read_raw(size)

    def readline(self, eol=None, timeout=None):
        raise NotImplementedError("still to come...")

    def write(self, msg, timeout=None):
        # signature from bliss socket
        # timeout so far ignored
        return self._instrument.write_raw(msg)

    def write_read(self, msg, write_synchro=None, size=-1, timeout=None):
        self._instrument.write_raw(msg)
        if write_synchro:
            write_synchro.notify()
        return self._instrument.read_raw(size)

    def write_readline(self, msg, write_synchro=None, eol=None, timeout=None):
        # signature from bliss socket
        # imeout so far ignored
        local_eol = eol or self._eol

        self._instrument.write_raw(msg)
        if write_synchro:
            write_synchro.notify()
        res = self._instrument.read_raw()
        eol_pos = res.find(local_eol)
        if eol_pos == -1:
            raise RuntimeError("readline not fully implemented yet")
        return res[:eol_pos]

    def write_readlines(
        self, msg, nb_lines, write_synchro=None, eol=None, timeout=None
    ):
        raise NotImplementedError("still to come...")

    def flush(self):
        raise NotImplementedError("still to come...")

    def abort(self):
        self.instrument.abort()
