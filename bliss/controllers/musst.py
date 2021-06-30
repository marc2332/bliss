# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import weakref
import os
import hashlib
import functools
import numpy
import gevent

from itertools import chain

from bliss import global_map
from bliss.comm import get_comm
from bliss.common.utils import autocomplete_property
from bliss.common.greenlet_utils import KillMask, protect_from_kill
from bliss.config.channels import Cache
from bliss.config.conductor.client import remote_open
from bliss.common.switch import Switch as BaseSwitch
from bliss.controllers.counter import CounterController
from bliss.scanning.acquisition.musst import MusstDefaultAcquisitionMaster
from bliss.common.counter import Counter, SamplingCounter
from bliss.controllers.counter import SamplingCounterController, counter_namespace
from bliss.controllers.bliss_controller import BlissController


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


def _reset_cmd():
    def exec_cmd(self):
        try:
            return self.putget("RESET")
        finally:
            self._musst__last_md5.value = None

    return property(exec_cmd, doc="Musst reset")


def lazy_init(func):
    @functools.wraps(func)
    def f(self, *args, **kwargs):
        if self._channels is None:
            self._channels_init(self.config)
        return func(self, *args, **kwargs)

    return f


class MusstSamplingCounter(SamplingCounter):
    def __init__(self, name, channel, convert, controller, **kwargs):
        SamplingCounter.__init__(self, name, controller, **kwargs)
        self.channel = channel
        self.convert = convert


class MusstIntegratingCounter(Counter):
    def __init__(self, name, channel, convert, controller, **kwargs):
        super().__init__(name, controller, **kwargs)
        self.channel = channel
        self.convert = convert


class MusstSamplingCounterController(SamplingCounterController):
    def __init__(self, musst):
        super().__init__(musst.name, register_counters=False)
        self.musst_ctrl = musst
        # High frequency acquisition loop
        self.max_sampling_frequency = None

    def read_all(self, *counters):
        """ return the values of the given counters as a list.
            If possible this method should optimize the reading of all counters at once.
        """
        return self.musst_ctrl.read_all(*counters)


class MusstIntegratingCounterController(CounterController):
    def __init__(self, musst):
        super().__init__(name=musst.name, register_counters=False)
        self.musst = musst

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return MusstDefaultAcquisitionMaster(
            self, self.musst, ctrl_params=ctrl_params, **acq_params
        )

    def get_default_chain_parameters(self, scan_params, acq_params):
        return {"count_time": acq_params.get("count_time", scan_params["count_time"])}


class musst(BlissController):
    class channel(object):
        COUNTER, ENCODER, SSI, ADC10, ADC5, SWITCH = list(range(6))

        def __init__(self, musst, channel_id, type=None, switch=None, switch_name=None):
            self._musst = weakref.ref(musst)
            self._channel_id = channel_id
            self._mode_number = None
            self._string2mode = {
                "CNT": self.COUNTER,
                "ENCODER": self.ENCODER,
                "SSI": self.SSI,
                "ADC10": self.ADC10,
                "ADC5": self.ADC5,
                "SWITCH": self.SWITCH,
                "ENC": self.ENCODER,
            }
            self._mode2string = [
                "CNT",
                "ENCODER",
                "SSI",
                "ADC10",
                "ADC5",
                "SWITCH",
                "ENC",
            ]
            if type is not None:
                if isinstance(type, str):
                    MODE = type.upper()
                    mode = self._string2mode.get(MODE)
                    if mode is None:
                        raise RuntimeError("musst: mode (%s) is not known" % type)
                    self._mode_number = mode
                else:
                    self._mode_number = type
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
        def mode(self):
            return self._mode_number

        @property
        def mode_str(self):
            return self._mode2string[self._mode_number]

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
        def status_string(self):
            musst = self._musst()
            status_string = musst.putget("?CH CH%d" % self._channel_id).split()[1]
            return status_string

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
            if self._mode_number == self.COUNTER or self._mode_number == self.ENCODER:
                musst = self._musst()
                musst.putget("CH CH%d %s" % (self._channel_id, cmd))
            else:
                raise RuntimeError(
                    "%s command on "
                    "channel %d is not allowed in this mode" % (cmd, self._channel_id)
                )

        def _convert(self, string_value):
            """Return channel value, converted according to the configured mode.
            """
            self._read_config()
            if self._mode_number == self.COUNTER:
                return int(string_value)
            elif self._mode_number == self.ADC10:
                return int(string_value) * (10. / 0x7fffffff)
            elif self._mode_number == self.ADC5:
                return int(string_value) * (5. / 0x7fffffff)
            else:  # not managed yet
                return int(string_value)

        def _read_config(self):
            """Read configuration of the current channel from MUSST board to
            determine the usage mode of the channel.
            Fill self._mode_number attribute.
            """
            if self._mode_number is None:
                musst = self._musst()
                string_config = musst.putget("?CHCFG CH%d" % self._channel_id)
                split_config = string_config.split()
                self._mode_number = self._string2mode.get(split_config[0])
                if self._mode_number == self.ADC10:  # TEST if it's not a 5 volt ADC
                    if len(split_config) > 1 and split_config[1].find("5") > -1:
                        self._mode_number = self.ADC5

    ADDR = _get_simple_property("ADDR", "Set/query serial line address")
    BTRIG = _get_simple_property(
        "BTRIG", "Set/query the level of the TRIG out B output signal"
    )
    NAME = _get_simple_property("NAME", "Set/query module name")
    EBUFF = _get_simple_property("EBUFF", "Set/ query current event buffer")
    HBUFF = _get_simple_property("HBUFF", "Set/ query current histogram buffer")

    ABORT = _simple_cmd("ABORT", "Program abort")
    STOP = _simple_cmd("STOP", "Program stop")
    RESET = _reset_cmd()
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
    NOPROG_STATE, BADPROG_STATE, IDLE_STATE, RUN_STATE, BREAK_STATE, STOP_STATE, ERROR_STATE = list(
        range(7)
    )
    # FREQUENCY TIMEBASE
    F_1KHZ, F_10KHZ, F_100KHZ, F_1MHZ, F_10MHZ, F_50MHZ = list(range(6))

    def __init__(self, config):
        """Base Musst controller.

        config           -- controller configuration
          url            -- url of the gpib controller i.s:enet://gpib0.esrf.fr
          pad            -- primary address of the musst controller
          timeout        -- communication timeout in seconds, default is 1s
          eos            -- end of line termination
        musst_prg_root      -- default path for musst programs
        block_size          -- default is 8k but can be lowered to 512 depend on gpib.
        one_line_programing -- default is False we send several lines to program the musst
        channels:           -- list of configured channels in this dictionary we need to have:
          label:              -- the name alias for the channels
          type:               -- channel type (cnt,encoder,ssi,adc5,adc10 and switch)
          channel:            -- channel number
          name:               -- use to reference an external switch
        """

        super().__init__(config)

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

        self._channels = None
        self._timer_factor = None

        self._last_run = time.time()
        global_map.register(self, parents_list=["counters"])

    def _load_config(self):

        self.__last_md5 = Cache(self, "last__md5")
        self.__event_buffer_size = Cache(self, "event_buffer_size")
        self.__prg_root = self.config.get("musst_prg_root")
        self.__block_size = self.config.get("block_size", 8 * 1024)
        self.__one_line_programing = self.config.get(
            "one_line_programing", "serial_url" in self.config
        )

        self._counter_controllers = {}
        self._counter_controllers["scc"] = MusstSamplingCounterController(self)
        self._counter_controllers["icc"] = MusstIntegratingCounterController(self)

        max_freq = self.config.get("max_sampling_frequency")
        self._counter_controllers["scc"].max_sampling_frequency = max_freq

    def _init(self):
        # Called by bliss_controller plugin (just after self._load_config)

        """
            Place holder for any action to perform after the configuration has been loaded.
        """
        gpib = self.config.get("gpib")
        comm_opts = dict()
        if gpib:
            gpib["eol"] = ""
            comm_opts["timeout"] = 5
            self._txterm = b""
            self._rxterm = b"\n"
            self._binary_data_read = True
        else:
            self._txterm = b"\r"
            self._rxterm = b"\r\n"
            self._binary_data_read = False

        self._cnx = get_comm(self.config, **comm_opts)

    def _get_default_chain_counter_controller(self):
        return self._counter_controllers["icc"]

    def _channels_init(self, config):
        """ Handle configured channels """

        self._channels = dict()
        channels_list = config.get("channels", list())
        for channel_config in channels_list:
            channel_number = channel_config.get("channel")
            channel = None
            if channel_number is None:
                raise RuntimeError("musst: channel in config must have a channel")
            elif channel_number in range(1, 7):
                channel_type = channel_config.get("type")
                if channel_type in ("cnt", "encoder", "ssi", "adc5", "adc10"):
                    channel_name = channel_config.get("label")
                    if channel_name is None:
                        raise RuntimeError("musst: channel in config must have a label")
                    channels = self._channels.setdefault(channel_name.upper(), list())
                    channel = self.get_channel(channel_number, type=channel_type)
                    channels.append(channel)
                elif channel_type == "switch":
                    ext_switch = channel_config.get("name")
                    if not hasattr(ext_switch, "states_list"):
                        raise RuntimeError(
                            "musst: channels (%s) switch object must have states_list method"
                            % channel_number
                        )
                    for channel_name in ext_switch.states_list():
                        channels = self._channels.setdefault(
                            channel_name.upper(), list()
                        )
                        channels.append(
                            self.get_channel(
                                channel_number,
                                type=channel_type,
                                switch=ext_switch,
                                switch_name=channel_name,
                            )
                        )
                # will read the musst config to know the type
                elif channel_type is None:
                    channel = self.get_channel(channel_number)
                else:
                    raise ValueError(
                        "musst: channel type can only be one of: (cnt,encoder,ssi,adc5,adc10,switch)"
                    )

            cnt_name = channel_config.get("counter_name")
            if cnt_name is not None:
                if channel is None:  # Must be TIMER
                    cnt_channel = "TIMER"
                    channel_type = self.channel.COUNTER

                    def convert(string_value):
                        if self._timer_factor is None:
                            self._timer_factor = self.get_timer_factor()
                        return int(string_value) / self._timer_factor

                else:
                    if channel_type == "switch":
                        # need to get the real type of musst channel
                        # so force musst config reading
                        channel = self.get_channel(channel_number)

                    cnt_channel = "CH%d" % channel._channel_id
                    channel._read_config()  # to fill the channel type
                    channel_type = channel._mode_number
                    if channel_type == "switch":

                        def convert(string_value):
                            value = channel._convert(string_value)
                            if hasattr(ext_switch, "convert"):
                                return ext_switch.convert(value)
                            return value

                    else:
                        convert = channel._convert

                if channel_type == self.channel.COUNTER:
                    self._counter_controllers["icc"].create_counter(
                        MusstIntegratingCounter, cnt_name, cnt_channel, convert
                    )
                else:
                    cnt_mode = channel_config.get("counter_mode", "MEAN")
                    self._counter_controllers["scc"].create_counter(
                        MusstSamplingCounter,
                        cnt_name,
                        cnt_channel,
                        convert,
                        mode=cnt_mode,
                    )

    @lazy_init
    def __info__(self):
        """Default method called by the 'BLISS shell default typing helper'
        """
        version = self.putget("?VER")
        timebase = self.putget("?TMRCFG")
        hmem, hbuf = self.putget("?HSIZE").split(" ")
        emem, ebuf = self.putget("?ESIZE").split(" ")
        info_str = f"MUSST card: {self.name}, {version}\n"
        info_str += self._cnx.__info__() + "\n"
        info_str += f"TIMEBASE: {timebase}\n"
        info_str += "MEMORY:\n"
        info_str += (
            f"         MCA:     size (32b values): {hmem:>8}, buffers: {hbuf:>8}\n"
        )
        info_str += (
            f"         STORAGE: size (32b values): {emem:>8}, buffers: {ebuf:>8}\n"
        )
        info_str += "CHANNELS:\n"

        # CYRIL [13]: musst_sxm.get_channel(6).status_string
        #  Out [13]: 'STOP'

        for ii in range(6):
            ch_idx = ii + 1
            ch_value, ch_status = self.putget(f"?CH CH{ch_idx}").split(" ")
            ch_config = self.putget(f"?CHCFG CH{ch_idx}")
            info_str += (
                f"         CH{ch_idx} ({ch_status:>4}): {ch_value:>10} -  {ch_config}\n"
            )

        return info_str

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
            self._cnx._write(msg.encode() + self._txterm)
            if msg.startswith("?") or ack:
                answer = self._cnx._readline(self._rxterm)
                if answer == b"$":
                    return self._cnx._readline(b"$" + self._rxterm).decode()
                elif ack:
                    if answer != b"OK":
                        raise RuntimeError("%s: invalid answer: %r", self.name, answer)
                    return True
                else:
                    return answer.decode()

    def _wait(self):
        while self.STATE == self.RUN_STATE:
            gevent.sleep(0)

    def run(self, entryPoint=None, wait=False):
        """ Execute program.

        entryPoint -- program name or a program label that
        indicates the point from where the execution should be carried out
        """
        # DBG_EPTR        self._eptr_debug = list()
        if entryPoint is None:
            self.putget("#RUN")
        else:
            self.putget("#RUN %s" % entryPoint)
        if wait:
            self._wait()

    def ct(self, acq_time=None, wait=True):
        """Starts the system timer, all the counting channels
        and the MCA. All the counting channels
        are previously cleared.

        time -- If specified, the counters run for that time (in s.)
        """
        self._timer_factor = self.get_timer_factor()
        diff = time.time() - self._last_run
        if diff < 0.02:
            gevent.sleep(0.02 - diff)
        if acq_time is not None:
            time_clock = acq_time * self._timer_factor
            self.putget("#RUNCT %d" % time_clock)
        else:
            self.putget("#RUNCT")
        if wait:
            self._wait()
        self._last_run = time.time()

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

        self.upload_program(program_bytes, template_replacement)

    def __replace_using_template(self, program_bytes, template_replacement):
        for old, new in template_replacement.items():
            if isinstance(old, str):
                old = old.encode()
            if isinstance(new, str):
                new = new.encode()
            program_bytes = program_bytes.replace(old, new)
        return program_bytes

    def upload_program(self, program_data, template_replacement={}):
        """ Upload a program.

        program_data -- program data you want to upload
        """
        if isinstance(program_data, str):
            program_data = program_data.encode()
        program_data = self.__replace_using_template(program_data, template_replacement)
        m = hashlib.md5()
        m.update(program_data)
        md5sum = m.hexdigest()
        if self.__last_md5.value == md5sum:
            return

        self.putget("#CLEAR")
        if self.__one_line_programing:
            # split into lines for Prologix
            for l in program_data.splitlines():
                self._cnx.write(b"+%s\r\n" % l)
        else:
            prg = b"".join([b"+%s\r\n" % l for l in program_data.splitlines()])
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
        for idx in range(5):
            curr_state = self.STATE
            current_offset, current_buffer_id = self.get_event_memory_pointer()
            gevent.sleep(100e-3)
            next_offset, next_buffer_id = self.get_event_memory_pointer()
            if next_offset >= current_offset and next_buffer_id >= current_buffer_id:
                break
            if curr_state != self.RUN_STATE:
                break
            # DBG_EPTR            self._eptr_debug.append(
            # DBG_EPTR                f"get_data filter {current_offset} {current_buffer_id} {next_offset} {next_buffer_id}"
            # DBG_EPTR            )
            gevent.sleep(100e-3)  # wait a little bit before re-asking

        # DBG_EPTR        if idx > 0:
        # DBG_EPTR            self._eptr_debug.append(
        # DBG_EPTR                f"get_data keep {current_offset} {current_buffer_id}"
        # DBG_EPTR            )

        current_offset = current_buffer_id * buffer_size + current_offset

        from_offset = (from_event_id * nb_counters) % buffer_memory
        current_offset = current_offset // nb_counters * nb_counters
        if current_offset >= from_offset:
            nb_lines = (current_offset - from_offset) // nb_counters
            data = numpy.empty((nb_lines, nb_counters), dtype=numpy.int32)
            self._read_data(from_offset, current_offset, data)
        else:
            nb_lines = (buffer_memory - from_offset + current_offset) // nb_counters
            data = numpy.empty((nb_lines * nb_counters,), dtype=numpy.int32)
            self._read_data(from_offset, buffer_memory, data)
            self._read_data(0, current_offset, data[buffer_memory - from_offset :])
            data.shape = (nb_lines, nb_counters)
        # DBG_EPTR        self._eptr_debug.append(f"get_data read {nb_lines*nb_counters}")
        return data

    def _read_data(self, from_offset, to_offset, data):
        BLOCK_SIZE = self.__block_size
        total_int32 = to_offset - from_offset
        data_pt = data.flat
        dt = numpy.dtype(numpy.int32)
        for offset, data_offset in zip(
            range(from_offset, to_offset, BLOCK_SIZE), range(0, total_int32, BLOCK_SIZE)
        ):
            size_to_read = min(BLOCK_SIZE, total_int32)
            total_int32 -= BLOCK_SIZE
            if self._binary_data_read:
                with self._cnx._lock:
                    self._cnx.open()
                    with KillMask():
                        self._cnx._write(b"?*EDAT %d %d %d" % (size_to_read, 0, offset))
                        raw_data = b""
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
        event_buffer_size = self.__event_buffer_size.value
        if event_buffer_size is None:
            event_buffer_size = [int(x) for x in self.putget("?ESIZE").split()]
            self.__event_buffer_size.value = event_buffer_size
        return event_buffer_size

    def set_event_buffer_size(self, buffer_size, nb_buffer=1):
        """ set event buffer size.

        buffer_size -- request buffer size
        nb_buffer -- the number of allocated buffer
        """
        self.__event_buffer_size.value = None
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
        for idx in range(5):
            buff_values = self.get_event_buffer_size()
            eptr_values = [int(x) for x in self.putget("?EPTR").split()]
            if eptr_values == [64, 0] or eptr_values == [256, 0]:
                # DBG_EPTR                self._eptr_debug.append(
                # DBG_EPTR                    f"eptr read filter {eptr_values[0]} {eptr_values[1]}"
                # DBG_EPTR                )
                gevent.sleep(100e-3)
                eptr_values = [int(x) for x in self.putget("?EPTR").split()]
            # DBG_EPTR            self._eptr_debug.append(f"eptr read {eptr_values[0]} {eptr_values[1]}")
            if (
                eptr_values[0] < buff_values[0]
                and eptr_values[1] >= 0
                and eptr_values[1] < buff_values[1]
            ):
                break
            # DBG_EPTR            self._eptr_debug.append(f"eptr filter {eptr_values[0]} {eptr_values[1]}")
            gevent.sleep(100e-3)

        return eptr_values

    # DBG_EPTR    def dump_eptr_debug(self, filename):
    # DBG_EPTR        df = open(filename, "w")
    # DBG_EPTR        df.writelines(map(lambda x: x + "\n", self._eptr_debug))
    # DBG_EPTR        df.close()

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

    @lazy_init
    def get_channel(self, channel_id, type=None, switch=None, switch_name=None):
        if 0 < channel_id <= 6:
            return self.channel(
                self, channel_id, type=type, switch=switch, switch_name=switch_name
            )
        else:
            raise RuntimeError("musst doesn't have channel id %d" % channel_id)

    @lazy_init
    def get_channel_by_name(self, channel_name):
        """<channel_name>: Label of the channel.
        """
        channel_name = channel_name.upper()
        channels = self._channels.get(channel_name)
        if channels is None:
            raise RuntimeError(
                "musst doesn't have channel (%s) in his config" % channel_name
            )
        return channels[0]  # first match

    @lazy_init
    def get_channel_by_names(self, *channel_names):
        """<channel_names>: Labels of the channels.
        """
        channels = dict()
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
        return list(channels.values())

    # Add a read_all method to read counters
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
            val_float = [
                cnt.convert(val) for val, cnt in zip(val_str.split(" "), counters)
            ]

            return val_float

    @autocomplete_property
    @lazy_init
    def counters(self):
        cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        return counter_namespace(chain(*cnts))


# Musst switch
class Switch(BaseSwitch):
    """
    This class wrapped musst command to emulate a switch.

    The configuration may look like this:

    .. code-block::

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
        self.__states = dict()
        self.__state_test = dict()

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
        for test_cmd, test_reply in self.__state_test.items():
            reply = self.__musst.putget(test_cmd)
            state = test_reply.get(reply)
            if state is not None:
                return state
        return "UNKNOWN"

    def _states_list(self):
        return list(self.__states.keys())


class MusstMock(musst):
    class FakeCnx:
        def __init__(self):
            self._lock = gevent.lock.RLock()
            self.last_cmd = None

        def __info__(self):
            return "fake connection to a musst card"

        def open(self):
            pass

        def _readline(self, rxterm):
            cmd = self.last_cmd
            self.last_cmd = None
            # print(cmd)
            if cmd.startswith("?"):
                if cmd.startswith("?TMRCFG"):
                    return b"10KHZ"

                elif cmd.startswith("?HSIZE"):
                    return b"0 0"

                elif cmd.startswith("?ESIZE"):
                    return b"0 0"

                elif cmd.startswith("?VAR"):
                    return b"0"

                elif cmd.startswith("?LIST ERR"):
                    return b"".encode()

                elif cmd.startswith("?EDAT"):
                    return b"0 0 0 0 0 0 0 0 0 0 0"

                elif cmd.startswith("?VAL"):
                    return b"0 0 0 0 0 0 0 0 0 0 0"

                elif cmd.startswith("?VER"):
                    return b"fake card"

                elif cmd.startswith("?CHCFG"):
                    return b""

                elif cmd.startswith("?CH"):
                    h, v = cmd.split()
                    ch = int(v[2:])
                    return f"{ch} OK".encode()

                else:
                    return b"XX XX"
            else:
                return b"OK"

        def _write(self, bcmd):
            self.last_cmd = bcmd.decode().strip()

        def raw_read(self):
            return b""

    def _init(self):

        gpib = self.config.get("gpib")
        comm_opts = dict()
        if gpib:
            gpib["eol"] = ""
            comm_opts["timeout"] = 5
            self._txterm = b""
            self._rxterm = b"\n"
            self._binary_data_read = True
        else:
            self._txterm = b"\r"
            self._rxterm = b"\r\n"
            self._binary_data_read = False

        self._cnx = self.FakeCnx()
