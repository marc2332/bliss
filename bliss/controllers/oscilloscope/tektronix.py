# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2021 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# for inspiration have a look at
# https://github.com/tektronix/Programmatic-Control-Examples/tree/master/Examples/Oscilloscopes

from bliss.controllers.oscilloscope.base import (
    Oscilloscope,
    OscilloscopeHardwareController,
    OscilloscopeAnalogChannel,
    OscAnalogChanData,
    OscMeasData,
    OscilloscopeTrigger,
)

from bliss.comm.util import get_comm
from ruamel.yaml import YAML
import gevent
import numpy
from bliss.common.utils import autocomplete_property
from bliss.common.utils import deep_update
from functools import partial
import pprint


class ConfigNamespace(object):
    def __new__(cls, tree, device, prefix=None):
        cls = type(cls.__name__, (cls,), {})
        for key in tree:
            if isinstance(tree[key], dict):
                setattr(
                    cls,
                    key,
                    autocomplete_property(
                        fget=partial(ConfigNamespace._getter, key=key),
                        fset=partial(ConfigNamespace._setter, key=key),
                    ),
                )
            else:
                # to avoid autocompletion for the final values ...
                setattr(
                    cls,
                    key,
                    property(
                        fget=partial(ConfigNamespace._getter, key=key),
                        fset=partial(ConfigNamespace._setter, key=key),
                    ),
                )
        return object.__new__(cls)

    def _setter(self, value, key):
        cmd = ":" + ":".join(self._prefix) + ":" + key + " " + str(value) + ";"
        self._device.write(cmd)

    def _getter(self, key):
        value = self._tree[key]
        if isinstance(value, dict):
            return ConfigNamespace(value, self._device, [*self._prefix, key])
        return self._tree[key]

    def __init__(self, tree, device, prefix=None):
        if prefix is None:
            self._prefix = list()
        else:
            self._prefix = prefix
        self._tree = tree
        self._device = device

    def __info__(self):
        return pprint.pformat(self._tree, indent=2)


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

    def _complete_keys(self, index, last_prefix, sequence, final):
        """
            Compound Commands

There can be more than one SCPI command on the same command line. This is done by entering the commands separated by a semi-colon (;). For example:
MEASURE:VOLTAGE:DC?;DC:RATIO?

This is equivalent to the following two commands:
MEASURE:VOLTAGE:DC?
MEASURE:VOLTAGE:DC:RATIO?

A feature of compound commands is that the following command starts at the last node of the previous command. This often makes the command line shorter than it would be otherwise. But what if you want a to use a command on a different branch?

If this is the case, you must put a colon (:) before the command that follows the semi-colon (;). This returns the command tree to the root. For example this is a valid command line:
MEASURE:VOLTAGE:DC?;:MEASURE:CURRENT:DC? 
            """
        c = sequence[index]
        if ":" in c and " " in c:
            if c.index(":") < c.index(" "):
                new_prefix, new_command = c.split(":", 1)
                sequence[index] = new_command
                self._complete_keys(
                    index, last_prefix + ":" + new_prefix, sequence, final
                )
                return
        elif ('"' in c and " " in c and c.index('"') > c.index(" ")) or (
            '"' not in c and " " in c
        ):
            new_prefix, value = c.split(" ", 1)
            final[last_prefix + ":" + new_prefix] = value
        else:
            final[last_prefix] = c

        if len(sequence) > index + 1:
            self._complete_keys(index + 1, last_prefix, sequence, final)

    def header_to_dict(self, header_string):
        # a good examples to see if this code is working are TRIGGER? and :WFMOutpre? and HORIZONTAL?

        if not hasattr(self, "_yaml"):
            self._yaml = YAML(pure=True)
        if isinstance(header_string, bytes):
            header_string = header_string.decode()
        res = dict()
        for top_level_entry in header_string.strip(":\n").split(";:"):
            seq = top_level_entry.split(";")
            self._complete_keys(0, "", seq, res)

        res2 = dict()
        for key, value in res.items():
            yml = ""
            count = 0
            for p in key.strip(":").split(":"):
                yml += " " * count + p + ":\n"
                count += 1
            yml += " " * count
            yml = yml.strip("\n") + " " + value
            tmp = self._yaml.load(yml)
            deep_update(res2, tmp)

        return res2

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

    def acq_prepare(self):
        pass

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
        header = header["WFMOUTPRE"]

        raw_data = numpy.frombuffer(datastring, dtype=numpy.int16)[-length:]
        data = (raw_data.astype(float) - header["YOFF"]) * header["YMULT"] + header[
            "YZERO"
        ]

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

    @autocomplete_property
    def trigger(self):
        return TektronixTrigger(self._device)

    @autocomplete_property
    def full_trigger_api(self):
        tree = self.device.header_to_dict(self.device.write_read(":Trigger?"))
        return ConfigNamespace(tree["TRIGGER"], self.device, ["TRIGGER"])

    @autocomplete_property
    def full_horizontal_api(self):
        tree = self.device.header_to_dict(self.device.write_read(":HORIZONTAL?"))
        return ConfigNamespace(tree["HORIZONTAL"], self.device, ["HORIZONTAL"])


class TektronixTrigger(OscilloscopeTrigger):
    def __info__(self):
        current = self._get_settings()
        return (
            f"tigger info \n"
            + f"source: {current['TRIGGER']['A']['EDGE']['SOURCE']}  possible:({self._device.get_channel_names()}) \n"
            #      + f"type:   {current['TYPE']}"
        )

    def _get_settings(self):
        return self._device.header_to_dict(self._device.write_read("TRIGGER?"))

    def get_current_setting(self, param):
        current = self._get_settings()
        return current[param.upper()]

    def set_trigger_setting(self, param, value):
        if param == "source":
            self._device.write(f":TRIGGER:A:EDGE:{param.upper()} {value};")
        else:
            raise NotImplementedError
