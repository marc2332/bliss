# --encoding: utf-8--
import time
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango import AttrWriteType
from tango import DevState


class Serial(Device):
    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

        self.buf = b""
        self.eol = None
        self.set_state(DevState.ON)

    @command(dtype_in="DevVarLongArray")
    def DevSerSetParameter(self, args):
        return

    @command(dtype_in=int)
    def DevSerSetNewline(self, eol):
        self.eol = chr(eol).encode()  # convert to bytes

    @command(dtype_out=bytearray)
    def DevSerReadLine(self):
        new_buf = self.buf.split(self.eol, 1)
        if len(new_buf) <= 1:
            # no line
            return ("", b"")
        self.buf = self.eol.join(new_buf[1:])
        return ("", new_buf[0])

    @command(dtype_in=int, dtype_out=bytearray)
    def DevSerReadNChar(self, maxsize):
        data = self.buf[:maxsize]
        self.buf = self.buf[len(data) :]
        return ("", data)

    @command(dtype_out=bytearray)
    def DevSerReadRaw(self):
        data = self.buf
        self.buf = b""
        return ("", data)

    @command(dtype_in=bytearray)
    def DevSerWriteChar(self, encoded_chars):
        chars = encoded_chars[
            1
        ].encode()  # convert string to bytes... see github issue #280
        self.buf += chars

    @command(dtype_in=int)
    def DevSerFlush(self, input):
        self.buf = b""

    @command(dtype_out=str)
    def status(self):
        return "ON"


if __name__ == "__main__":
    run((Serial,))
