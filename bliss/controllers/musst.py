# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import weakref
import os
import gevent
import hashlib
from bliss.comm.gpib import Gpib
from bliss.comm import serial
from bliss.common.greenlet_utils import KillMask, protect_from_kill
from bliss.config.channels import Cache
from bliss.config.conductor.client import remote_open
from bliss.common.switch import Switch as BaseSwitch
from bliss.common.utils import OrderedDict
from bliss.common.measurement import SamplingCounter, counter_namespace

Serial = serial.Serial


def _get_simple_property(command_name, doc_sring):
    def get(self):
        return self.putget("?%s" % command_name)

    def set(self, value):
        return self.putget("%s %s" % (command_name, value))

    return property(get, set, doc=doc_sring)


def _simple_cmd(command_name, doc_sring):
    def exec_cmd(self):
        return self.putget(command_name)

    return property(exec_cmd, doc=doc_sring)


def _clear_cmd():
    def exec_cmd(self):
        try:
            return self.putget("CLEAR")
        finally:
            self._musst__last_md5.value = None

    return property(exec_cmd, doc="Delete the current program")


class MusstCounter(SamplingCounter):
    def __init__(self, name, musst, channel):
        SamplingCounter.__init__(self, name, musst)
        self.channel = channel


class musst(object):
    class channel(object):
        COUNTER, ENCODER, SSI, ADC10, ADC5, SWITCH = range(6)

        def __init__(self, musst, channel_id, type=None, switch=None, switch_name=None):
            self._musst = weakref.ref(musst)
            self._channel_id = channel_id
            self._mode = None
            self._string2mode = {
                "CNT": self.COUNTER,
                "ENCODER": self.ENCODER,
                "SSI": self.SSI,
                "ADC10": self.ADC10,
                "ADC5": self.ADC5,
                "SWITCH": self.SWITCH,
            }
            if type is not None:
                if isinstance(type, (str, unicode)):
                    MODE = type.upper()
                    mode = self._string2mode.get(MODE)
                    if mode is None:
                        raise RuntimeError("musst: mode (%s) is not known" % type)
                    self._mode = mode
                else:
                    self._mode = type
            if switch is not None:
                # check if has the good interface
                if switch_name is None:
                    raise RuntimeError(
                        "musst: channel (%d) with external switch musst have a switch_name defined"
                        % channel_id
                    )
                if not hasattr(switch, "set"):
                    raise RuntimeError(
                        "musst: channel (%d), switch object doesn't have a set method"
                        % channel_id
                    )
                self._switch = switch
                self._switch_name = switch_name
            else:
                self._switch = None

        @property
        def value(self):
            if self._switch is not None:
                self._switch.set(self._switch_name)
            musst = self._musst()
            string_value = musst.putget("?CH CH%d" % self._channel_id).split()[0]
            return self._convert(string_value)

        @value.setter
        def value(self, val):
            if self._switch is not None:
                self._switch.set(self._switch_name)
            musst = self._musst()
            musst.putget("CH CH%d %s" % (self._channel_id, val))

        @property
        def status(self):
            musst = self._musst()
            status_string = musst.putget("?CH CH%d" % self._channel_id).split()[1]
            return musst._string2state.get(status_string)

        @property
        def channel_id(self):
            if self._switch is not None:
                self._switch.set(self._switch_name)
            return self._channel_id

        @property
        def switch(self):
            return self._switch

        def run(self, program_name=None):
            if program_name is None:
                self._cnt_cmd("RUN")
            else:
                self._cnt_cmd("RUN %s" % program_name)

        def stop(self):
            self._cnt_cmd("STOP")

        def _cnt_cmd(self, cmd):
            self._read_config()
            if self._mode == self.COUNTER or self._mode == self.ENCODER:
                musst = self._musst()
                musst.putget("CH CH%d %s" % (self._channel_id, cmd))
            else:
                raise RuntimeError(
                    "%s command on "
                    "channel %d is not allowed in this mode" % (cmd, self._channel_id)
                )

        def _convert(self, string_value):
            self._read_config()
            if self._mode == self.COUNTER:
                return int(string_value)
            elif self._mode == self.ADC10:
                return int(string_value) * (10. / 0x7fffffff)
            elif self._mode == self.ADC5:
                return int(string_value) * (5. / 0x7fffffff)
            else:  # not managed yet
                return int(string_value)

        def _read_config(self):
            if self._mode is None:
                musst = self._musst()
                string_config = musst.putget("?CHCFG CH%d" % self._channel_id)
                split_config = string_config.split()
                self._mode = self._string2mode.get(split_config[0])
                if self._mode == self.ADC10:  # TEST if it's not a 5 volt ADC
                    if len(split_config) > 1 and split_config[1].find("5") > -1:
                        self._mode = self.ADC5

    ADDR = _get_simple_property("ADDR", "Set/query serial line address")
    BTRIG = _get_simple_property(
        "BTRIG", "Set/query the level of the TRIG out B output signal"
    )
    NAME = _get_simple_property("NAME", "Set/query module name")
    EBUFF = _get_simple_property("EBUFF", "Set/ query current event buffer")
    HBUFF = _get_simple_property("HBUFF", "Set/ query current histogram buffer")

    ABORT = _simple_cmd("ABORT", "Program abort")
    STOP = _simple_cmd("STOP", "Program stop")
    RESET = _simple_cmd("RESET", "Musst reset")
    CONT = _simple_cmd(
        "CONT", "Continue the program when stopped in STOP or BREAK states"
    )
    CLEAR = _clear_cmd()
    LIST = _simple_cmd("?LIST CODE", "List the current program")
    LISTVAR = _simple_cmd("?LIST VAR", "List the current program")
    DBINFO = _simple_cmd("?DBINFO *", "Returns the list of installed daughter boards")
    HELP = _simple_cmd("?HELP", "Query list of available commands")
    INFO = _simple_cmd("?INFO", "Query module configuration")
    RETCODE = _simple_cmd("?RETCODE", "Query exit or stop code")
    TIMER = _simple_cmd("?TIMER", "Query timer")
    VAL = _simple_cmd("?VAL", "Query values")

    VARINIT = _simple_cmd("VARINIT", "Reset program variables")

    # STATE
    NOPROG_STATE, BADPROG_STATE, IDLE_STATE, RUN_STATE, BREAK_STATE, STOP_STATE, ERROR_STATE = range(
        7
    )
    # FREQUENCY TIMEBASE
    F_1KHZ, F_10KHZ, F_100KHZ, F_1MHZ, F_10MHZ, F_50MHZ = range(6)

    def __init__(self, name, config_tree):
        """Base Musst controller.

        name -- the controller's name
        config_tree -- controller configuration,
        in this dictionary we need to have:
        gpib_url -- url of the gpib controller i.s:enet://gpib0.esrf.fr
        gpib_pad -- primary address of the musst controller
        gpib_timeout -- communication timeout, default is 1s
        gpib_eos -- end of line termination
        musst_prg_root -- default path for musst programs
        block_size -- default is 8k but can be lowered to 512 depend on gpib.
        one_line_programing -- default is False we send several lines 
                               to program the musst
        channels: -- list of configured channels
        in this dictionary we need to have:
        label: -- the name alias for the channels
        type: -- channel type (cnt,encoder,ssi,adc5,adc10 and switch)
        channel: -- channel number
        name: -- use to reference an external switch
        """

        self.name = name
        if "gpib_url" in config_tree:
            self._cnx = Gpib(
                config_tree["gpib_url"],
                pad=config_tree["gpib_pad"],
                eos=config_tree.get("gpib_eos", ""),
                timeout=config_tree.get("gpib_timeout", 5),
            )
            self._txterm = ""
            self._rxterm = "\n"
            self._binary_data_read = True
        elif "serial_url" in config_tree:
            self._cnx = Serial(config_tree["serial_url"])
            self._txterm = "\r"
            self._rxterm = "\r\n"
            self._binary_data_read = False
        else:
            raise ValueError, "Must specify gpib_url or serial_url"

        self._string2state = {
            "NOPROG": self.NOPROG_STATE,
            "BADPROG": self.BADPROG_STATE,
            "IDLE": self.IDLE_STATE,
            "RUN": self.RUN_STATE,
            "BREAK": self.BREAK_STATE,
            "STOP": self.STOP_STATE,
            "ERROR": self.ERROR_STATE,
        }

        self.__frequency_conversion = {
            self.F_1KHZ: ("1KHZ", 1e3),
            self.F_10KHZ: ("10KHZ", 10e3),
            self.F_100KHZ: ("100KHZ", 100e3),
            self.F_1MHZ: ("1MHZ", 1e6),
            self.F_10MHZ: ("10MHZ", 10e6),
            self.F_50MHZ: ("50MHZ", 50e6),
            "1KHZ": self.F_1KHZ,
            "10KHZ": self.F_10KHZ,
            "100KHZ": self.F_100KHZ,
            "1MHZ": self.F_1MHZ,
            "10MHZ": self.F_10MHZ,
            "50MHZ": self.F_50MHZ,
        }
        self.__last_md5 = Cache(self, "last__md5")
        self.__prg_root = config_tree.get("musst_prg_root")
        self.__block_size = config_tree.get("block_size", 8 * 1024)
        self.__one_line_programing = config_tree.get(
            "one_line_programing", "serial_url" in config_tree
        )

        # Configured channels
        self._channels = OrderedDict()
        channels_list = config_tree.get("channels", list())
        for channel_config in channels_list:
            channel_number = channel_config.get("channel")
            if channel_number is None:
                raise RuntimeError("musst: channel in config must have a channel")

            channel_type = channel_config.get("type")
            if channel_type in ("cnt", "encoder", "ssi", "adc5", "adc10"):
                channel_name = channel_config.get("label")
                if channel_name is None:
                    raise RuntimeError("musst: channel in config must have a label")
                channels = self._channels.setdefault(channel_name.upper(), list())
                channels.append(self.get_channel(channel_number, type=channel_type))
            elif channel_type == "switch":
                ext_switch = channel_config.get("name")
                if not hasattr(ext_switch, "states_list"):
                    raise RuntimeError(
                        "musst: channels (%s) switch object must have states_list method"
                        % channel_number
                    )

                for channel_name in ext_switch.states_list():
                    channels = self._channels.setdefault(channel_name.upper(), list())
                    channels.append(
                        self.get_channel(
                            channel_number,
                            type=channel_type,
                            switch=ext_switch,
                            switch_name=channel_name,
                        )
                    )
            else:
                raise ValueError(
                    "musst: channel type can only be one of: (cnt,encoder,ssi,adc5,adc10,switch)"
                )

        # Configured counters
        cnt_list = list()
        for cnt_config in config_tree.get("counters", list()):
            cnt_name = cnt_config.get("name")
            cnt_channel = cnt_config.get("channel")

            if cnt_channel.upper() not in (
                "TIMER",
                "CH1",
                "CH2",
                "CH3",
                "CH4",
                "CH5",
                "CH6",
            ):
                raise ValueError(
                    'Musst Counter: counter "%s" channel name (%s) must be [CH1/CH2/CH3/CH4/CH5/CH6]'
                    % (cnt_name, cnt_channel)
                )

            cnt_obj = MusstCounter(cnt_name, self, cnt_channel.upper())
            cnt_list.append(cnt_obj)
        self.__counters = counter_namespace(cnt_list)

    @property
    def counters(self):
        return self.__counters

    @protect_from_kill
    def putget(self, msg, ack=False):
        """ Raw connection to the Musst card.

        msg -- the message you want to send
        ack -- if True, wait the an acknowledge (synchronous)
        """

        if ack is True and not (msg.startswith("?") or msg.startswith("#")):
            msg = "#" + msg

        ack = msg.startswith("#")

        with self._cnx._lock:
            self._cnx.open()
            self._cnx._write(msg + self._txterm)
            if msg.startswith("?") or ack:
                answer = self._cnx._readline(self._rxterm)
                if answer == "$":
                    return self._cnx._readline("$" + self._rxterm)
                elif ack:
                    if answer != "OK":
                        raise RuntimeError("%s: invalid answer: %r", self.name, answer)
                    return True
                else:
                    return answer

    def _wait(self):
        while self.STATE == self.RUN_STATE:
            gevent.idle()

    def run(self, entryPoint=None, wait=False):
        """ Execute program.

        entryPoint -- program name or a program label that
        indicates the point from where the execution should be carried out
        """
        if entryPoint is None:
            self.putget("#RUN")
        else:
            self.putget("#RUN %s" % entryPoint)
        if wait:
            self._wait()

    def ct(self, time=None, wait=True):
        """Starts the system timer, all the counting channels
        and the MCA. All the counting channels
        are previously cleared.

        time -- If specified, the counters run for that time (in s.)
        """
        if time is not None:
            time *= self.get_timer_factor()
            self.putget("#RUNCT %d" % time)
        else:
            self.putget("#RUNCT")
        if wait:
            self._wait()

    def upload_file(self, fname, prg_root=None, template_replacement={}):
        """ Load a program into the musst device.

        fname -- the file-name
        prg_root -- the base path where the program files are.
        if prg_root is None use the one in configuration
        template_replacement -- will be used to replace the key by the value
        in the program file
        """
        prg_root = prg_root or self.__prg_root

        if prg_root:
            program_file = os.path.join(prg_root, fname)
        else:
            program_file = fname

        with remote_open(program_file) as program:
            program_bytes = program.read()
            for old, new in template_replacement.iteritems():
                program_bytes = program_bytes.replace(old, new)

        self.upload_program(program_bytes)

    def upload_program(self, program_data):
        """ Upload a program.

        program_data -- program data you want to upload
        """
        m = hashlib.md5()
        m.update(program_data)
        md5sum = m.hexdigest()
        if self.__last_md5.value == md5sum:
            return

        self.putget("#CLEAR")
        if self.__one_line_programing:
            # split into lines for Prologix
            for l in program_data.splitlines():
                self._cnx.write("+%s\r\n" % l)
        else:
            prg = "".join(["+%s\r\n" % l for l in program_data.splitlines()])
            self._cnx.write(prg)
        if self.STATE != self.IDLE_STATE:
            err = self.putget("?LIST ERR")
            raise RuntimeError(err)

        self.__last_md5.value = md5sum

        return True

    #    def get_data(self, nlines, npts, buf=0):
    def get_data(self, nb_counters, from_event_id=0):
        """ Read event musst data.

        nb_counters -- number counter you have in your program storelist
        from_event_id -- from which event you want to read

        Returns event data organized by event_id,counters
        """

        buffer_size, nb_buffer = self.get_event_buffer_size()
        buffer_memory = buffer_size * nb_buffer
        current_offset, current_buffer_id = self.get_event_memory_pointer()
        current_offset = current_buffer_id * buffer_size + current_offset

        from_offset = (from_event_id * nb_counters) % buffer_memory
        current_offset = current_offset / nb_counters * nb_counters
        if current_offset >= from_offset:
            nb_lines = (current_offset - from_offset) / nb_counters
            data = numpy.empty((nb_lines, nb_counters), dtype=numpy.int32)
            self._read_data(from_offset, current_offset, data)
        else:
            nb_lines = current_offset / nb_counters
            first_nblines = (buffer_memory - from_offset) / nb_counters
            nb_lines += first_nblines
            data = numpy.empty((nb_lines, nb_counters), dtype=numpy.int32)
            self._read_data(from_offset, buffer_memory, data)
            self._read_data(0, current_offset, data[first_nblines:])
        return data

    def _read_data(self, from_offset, to_offset, data):
        BLOCK_SIZE = self.__block_size
        total_int32 = to_offset - from_offset
        data_pt = data.flat
        dt = numpy.dtype(numpy.int32)
        for offset, data_offset in zip(
            xrange(from_offset, to_offset, BLOCK_SIZE),
            xrange(0, total_int32, BLOCK_SIZE),
        ):
            size_to_read = min(BLOCK_SIZE, total_int32)
            total_int32 -= BLOCK_SIZE
            if self._binary_data_read:
                with self._cnx._lock:
                    self._cnx.open()
                    with KillMask():
                        self._cnx._write("?*EDAT %d %d %d" % (size_to_read, 0, offset))
                        raw_data = ""
                        while len(raw_data) < (size_to_read * 4):
                            raw_data += self._cnx.raw_read()
                        data_pt[
                            data_offset : data_offset + size_to_read
                        ] = numpy.frombuffer(raw_data, dtype=numpy.int32)
            else:
                raw_data = self.putget("?EDAT %d %d %d" % (size_to_read, 0, offset))
                data_pt[data_offset : data_offset + size_to_read] = [
                    int(x, 16) for x in raw_data.split(self._rxterm) if x
                ]

    def get_event_buffer_size(self):
        """ query event buffer size.

        Returns buffer size and number of buffers
        """
        return [int(x) for x in self.putget("?ESIZE").split()]

    def set_event_buffer_size(self, buffer_size, nb_buffer=1):
        """ set event buffer size.

        buffer_size -- request buffer size
        nb_buffer -- the number of allocated buffer
        """
        return self.putget("ESIZE %d %d" % (buffer_size, nb_buffer))

    def get_histogram_buffer_size(self):
        """ query histogram buffer size.
        
        Returns buffer size and number of buffers
        """
        return [int(x) for x in self.putget("?HSIZE").split()]

    def set_histogram_buffer_size(self, buffer_size, nb_buffer=1):
        """ set histogram buffer size.

        buffer_size -- request buffer size
        nb_buffer -- the number of allocated buffer
        """
        return self.putget("HSIZE %d %d" % (buffer_size, nb_buffer))

    def get_event_memory_pointer(self):
        """Query event memory pointer.

        Returns the current position of the event data memory pointer (offset,buffN)
        """
        return [int(x) for x in self.putget("?EPTR").split()]

    def set_event_memory_pointer(self, offset, buff_number=0):
        """Set event memory pointer.

        Sets the internal event data memory pointer to point
        to the data position at offset <offset> in the buffer number <buff_number>.
        """
        return self.putget("EPTR %d %d" % (offset, buff_number))

    def get_variable_info(self, name):
        return self.putget("?VARINFO %s" % name)

    def get_variable(self, name):
        return float(self.putget("?VAR %s" % name))

    def set_variable(self, name, val):
        self.putget("VAR %s %s" % (name, val))

    @property
    def STATE(self):
        """ Query module state """
        return self._string2state.get(self.putget("?STATE"))

    @property
    def TMRCFG(self):
        """ Set/query main timer timebase """
        return self.__frequency_conversion[
            self.__frequency_conversion.get(self.putget("?TMRCFG"))
        ]

    def get_timer_factor(self):
        str_freq, freq = self.TMRCFG
        return freq

    @TMRCFG.setter
    def TMRCFG(self, value):
        if value not in self.__frequency_conversion:
            raise ValueError("Value not allowed")

        if not isinstance(value, str):
            value = self.__frequency_conversion.get(value)
        return self.putget("TMRCFG %s" % value)

    def get_channel(self, channel_id, type=None, switch=None, switch_name=None):
        if 0 < channel_id <= 6:
            return self.channel(
                self, channel_id, type=type, switch=switch, switch_name=switch_name
            )
        else:
            raise RuntimeError("musst doesn't have channel id %d" % channel_id)

    def get_channel_by_name(self, channel_name):
        channel_name = channel_name.upper()
        channels = self._channels.get(channel_name)
        if channels is None:
            raise RuntimeError(
                "musst doesn't have channel (%s) in his config" % channel_name
            )
        return channels[0]  # first match

    def get_channel_by_names(self, *channel_names):
        channels = OrderedDict()
        for channel_name in channel_names:
            chans = self._channels.get(channel_name.upper())
            if chans is None:
                raise RuntimeError(
                    "musst doesn't have channel (%s) in his config" % channel_name
                )
            else:
                for chan in chans:
                    if chan.channel_id not in channels:
                        channels[chan.channel_id] = chan
                        break
                else:
                    raise RuntimeError(
                        "Can't find a free channel for (%s)" % channel_name
                    )
        return channels.values()

    """
    Add read_all function to make Musst object a counter controller
    """

    def read_all(self, *counters):
        if len(counters) > 0:
            read_cmd = ""
            for cnt in counters:
                read_cmd = read_cmd + " " + cnt.channel
            read_cmd = "?VAL " + read_cmd
            val_str = self.putget(read_cmd)
            if val_str == "ERROR":
                raise RuntimeError(
                    "Musst (%s) Counter (%s): Error reading from Musst device"
                    % (cnt.controller.name, cnt.name)
                )
            val_float = [float(x) for x in val_str.split(" ")]

            return val_float


# Musst switch


class Switch(BaseSwitch):
    """
    This class wrapped musst command to emulate a switch.
    the configuration may look like this:
    musst: $musst_name
    states:
       - label: OPEN
         set_cmd: "#BTRIG 1"
         test_cmd: "?BTRIG"
         test_cmd_reply: "1"
       - label: CLOSED
         set_cmd: "#BTRIG 0"
         test_cmd: "?BTRIG"
         test_cmd_reply: "0"
    """

    def __init__(self, name, config):
        BaseSwitch.__init__(self, name, config)
        self.__musst = None
        self.__states = OrderedDict()
        self.__state_test = OrderedDict()

    def _init(self):
        config = self.config
        self.__musst = config["musst"]
        for state in config["states"]:
            label = state["label"]
            cmd = state["set_cmd"]
            self.__states[label] = cmd

            t1 = {state["test_cmd_reply"]: label}
            t = self.__state_test.setdefault(state["test_cmd"], t1)
            if t1 != t:
                t.update(t1)

    def _set(self, state):
        cmd = self.__states.get(state)
        if cmd is None:
            raise RuntimeError("State %s don't exist" % state)
        self.__musst.putget(cmd)

    def _get(self):
        for test_cmd, test_reply in self.__state_test.iteritems():
            reply = self.__musst.putget(test_cmd)
            state = test_reply.get(reply)
            if state is not None:
                return state
        return "UNKNOWN"

    def _states_list(self):
        return self.__states.keys()
