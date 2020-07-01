# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# for inspiration have a look at
# https://github.com/tektronix/Programmatic-Control-Examples/tree/master/Examples/Oscilloscopes

from bliss.controllers.oscilloscope import (
    Oscilloscope,
    OscilloscopeHardwareController,
    OscilloscopeAnalogChannel,
    OscAnalogChanData,
    OscMeasData,
)
from bliss.comm.util import get_comm
from ruamel.yaml import YAML
import gevent
import numpy


class TektronixOscCtrl(OscilloscopeHardwareController):
    # backend object not directly exposed to the user

    def __init__(self, name, config):
        self._comm = get_comm(config, eol=b"\n")

    def __close__(self):
        self._comm.close()

    def write_readline(self, message):
        ans = self.comm.write_readline((message + "\n").encode()).decode()
        return ans

    def write_read(self, message):
        ans = self.comm.write_read((message + "\n").encode()).decode()
        return ans

    def write(self, message):
        self.comm.write((message + "\n").encode())

    def strip(self, answer):
        # extract answer
        return answer.split(" ")[-1].strip()

    def idn(self):
        return self.write_readline("*idn?")

    def opc(self):
        stat = self.write_readline("*OPC?")
        if stat == "0":
            return False
        elif stat == "1":
            return True
        else:
            raise RuntimeError("unknown response!")

    def wait_ready(self, timeout=5):
        with gevent.timeout.Timeout(timeout):
            while not self.opc():
                gevent.sleep(.1)

    def busy(self):
        stat = self.strip(self.write_read("BUSY?"))
        if stat == "0":
            return False
        elif stat == "1":
            return True
        else:
            raise RuntimeError("unknown response!")

    def header_to_dict(self, header_string):
        if not hasattr(self, "_yaml"):
            self._yaml = YAML(pure=True)
            self._yaml.allow_duplicate_keys = True
        if isinstance(header_string, bytes):
            header_string = header_string.decode()
        yml = ""
        for entry in header_string.split(";"):
            first_space = entry.find(" ")
            key = entry[:first_space]
            value = entry[first_space + 1 :]
            yml += f"'{key}': {value}\n"
        return dict(self._yaml.load(yml))

    def get_channel_names(self):
        ### SAVe:WAVEform:SOURCEList? not the correct command ...
        ### ... how can I get ALL channels

        ### maybe better DATa:SOUrce:AVAILable?

        ans = self.write_read("DATa:SOUrce:AVAILable?")
        channels = self.strip(ans).split(",")
        #       if "ALL" in channels:
        #           channels.remove("ALL")
        return channels

    def get_measurement_names(self):
        ans = self.write_read("MEASUREMENT:LIST?")
        m = self.strip(ans).split(",")
        return m

    def acq_start(self):
        self.write("acquire:state 0")  # stop
        self.write("acquire:stopafter SEQUENCE")  # single
        self.write("acquire:state 1")  # run

    def acq_read_channel(self, name, length=None):
        # Wait for trigger...
        # still to be handeled...

        if length is None:
            length = int(self.strip(self.write_read("horizontal:recordlength?")))
        self.write(f":DATa:SOUrce {name}")
        self.write(":DATa:START 1")
        self.write(f":DATa:STOP {length}")
        self.write(":WFMOutpre:ENCdg BINARY")
        self.write(":WFMOutpre:BYT_Nr 2")
        self.write(":WFMOutpre:BYT_Or MSB")
        self.write(":HEADer 1")

        head = self.write_read(":WFMOutpre?")
        datastring = self._comm.write_read(b":CURVE?")  # raw binary comm
        header = self.header_to_dict(head)

        raw_data = numpy.frombuffer(datastring, dtype=numpy.int16)[-length:]
        data = (raw_data.astype(numpy.float) - header["YOFF"]) * header[
            "YMULT"
        ] + header["YZERO"]

        return OscAnalogChanData(length, raw_data, data, header)

    def acq_read_measurement(self, name):

        head = self.write_read(f"MEASUREMENT:{name}?")
        header = self.header_to_dict(head)
        val = self.strip(self.write_read(f"MEASUREMENT:{name}:VALUE?"))
        value = float(val)

        return OscMeasData(value, header)

    def acq_stop(self):
        pass
        # put back in continous aquisition

    def acq_done(self):
        return self.strip(self.write_read("ACQuire:STATE?")) == "0"


class TektronixAnalogChannel(OscilloscopeAnalogChannel):
    pass


class TektronixOsc(Oscilloscope):
    # user exposed object
    def __init__(self, name, config):
        self._device = TektronixOscCtrl(self, config)
        Oscilloscope.__init__(self, name, config)

    def _channel_counter(self, name):
        return TektronixAnalogChannel(name, self._counter_controller)

    def __close__(self):
        self._device.__close__()
