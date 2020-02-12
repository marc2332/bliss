# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent
import ctypes
import struct
import socket
import time
import collections
from itertools import zip_longest
import functools

from prompt_toolkit import print_formatted_text, HTML
from tabulate import tabulate

from bliss.common import tango

from bliss.common.utils import add_property, flatten
from bliss.config.conductor.client import synchronized
from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_debug, log_debug_data, log_error, log_exception
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import counter_namespace, SamplingCounterController
from bliss.controllers.wago.helpers import (
    splitlines,
    to_signed,
    to_unsigned,
    register_type_to_int,
)

from bliss.common.utils import ShellStr

"""
EXPLANATION AND NAMING CONVENTION

PHYSICAL MAPPING

Every Wago PLC is normally assembled with a central unit (Wago PLC Ethernet/IP type
750-842) plus a variable numbers of addons as needed.
Addon modules usually has one or more input/output that can be plugged to the outside
world.

Naming Convention:

 * PHYSICAL_MODULES: (int) hardware modules with I/O that you physically compose to
obtain the physical configuration, we will number them from 0 (first hardware module)
to n.
 * PHYSICAL_CHANNELS: (int) I/O inside one PHYSICAL_MODULE, we will number them from 0
(first channel) to n.

EXAMPLE

      **********************************
      *                                *
      *       PLC Central Unit         *
      *                                *
      **********************************
      *       Physical Module n.0      *  -> Physical Channel n.0
      *                                *
      *        2 Digital Output        *  -> Physical Channel n.1
      **********************************
      *       Physical Module n.1      *  -> Physical Channel n.0
      *                                *
      *        2 Digital Input         *  -> Physical Channel n.1
      **********************************
      *       Physical Module n.2      *  -> Physical Channel n.0
      *                                *  -> Physical Channel n.1
      *         4 Digital Output       *  -> Physical Channel n.2
      *                                *  -> Physical Channel n.3
      **********************************




LOGICAL MAPPING

We can define LOGICAL DEVICES that will group I/O of different kind and from
different physical modules.
This LOGICAL MAPPING will abstract the logic from the hardware.

Naming conventions:

 * LOGICAL_DEVICE: (string) is a mnemonic string that identify the device like:
   foh2ctrl, esTf1, pres, sain6.
 * LOGICAL_DEVICE_KEY: (int) an enumeration of logical devices where first logical
   device will have device key 0, second logical device will have device key 1 and so on.
 * LOGICAL_CHANNEL: (int) every Logical Device can have multiple channels that are 
   numbered from 0. One logical channel will map to a Physical Channel

Example taken from a configuration:
    Config:
        750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl
        750-408, foh2pos, sain2, foh2pos, sain2
        750-408, foh2pos, sain6, foh2pos, sain8

    Explanation:
        We have 5 logical devices: foh2ctrl, foh2pos, sain2, sain6, sain8.
        foh2ctrl has 4 logical channel from 0 to 3, they are situated in the
                 physical module n.0 respectively on physical channels from 0 to 3
        foh2pos has 4 logical channel from 0 to 1, two logical channels are situated
                on physical module n.1 (channels n.0 and n.2) and two are situated
                on physical module n.2 (channels n.0 and n.2)
        sain2 has 2 logical channels situated on physical module n.1 on channels n.1
              and n.3
        sain6 has 1 logical channel situated on physical module n.2 on channel n.1
        sain8 has 1 logical channel situated on physical module n.2 on channel n.3


"""


WAGO_COMMS = {}


DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT, N_CHANNELS, N_CHANNELS_EXT, READING_TYPE, DESCRIPTION, READING_INFO, WRITING_INFO = (
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
)

ERRORS = {
    1: "Communication timeout",
    2: "Bad command",
    3: "Bad parameter(s)",
    4: "Bad instance number",
    5: "Instance is not enabled",
    6: "No more instances available",
    7: "Bad Function",
    8: "Bad channel",
    9: "No more channels available",
}
ModConf = collections.namedtuple(
    "ModConf",
    "digi_in digi_out ana_in ana_out n_channels n_channels_ext reading_type description reading_info writing_info".split(),
)

MODULES_CONFIG = {
    # [Digital IN, Digital OUT, Analog IN, Analog OUT, Total_normal_mode, Total_extended_mode, type]
    # types are:
    # fs4-20: 4/20mA
    # fs20: 4/20mA
    # fs10: 0/10V
    # thc: thermocouple
    # ssi24: 24 bit SSI encoder
    # ssi32: 32 bit SSI encoder
    # digital: digital IN or OUT
    # counter: counters
    "750-842": [0, 0, 0, 0, 2, 2, "cpu", "Wago PLC Ethernet/IP"],
    "750-881": [0, 0, 0, 0, 2, 2, "cpu", "Wago PLC Ethernet/IP"],
    "750-891": [0, 0, 0, 0, 2, 2, "cpu", "Wago PLC Ethernet/IP"],
    "750-400": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-401": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-402": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-403": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    # Input process image has 2 words of counter value and 1 byte of status,
    # total of 3 words
    # Output process image has 2 words of counter setting value and 1 byte of
    # control, total of 3 words
    "750-404": [
        0,
        0,
        3,
        3,
        2,
        4,
        "counter",
        "32 bit Counter",
    ],  # special #TODO: check this
    "750-405": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-406": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-408": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-409": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-410": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-411": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-412": [2, 0, 0, 0, 2, 2, "digital", "2 Channel Digital Input"],
    "750-414": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-415": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-422": [4, 0, 0, 0, 4, 4, "digital", "4 Channel Digital Input"],
    "750-430": [8, 0, 0, 0, 8, 8, "digital", "8 Channel Digital Input"],
    "750-436": [8, 0, 0, 0, 8, 8, "digital", "8 Channel Digital Input"],
    "750-452": [0, 0, 2, 0, 2, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-454": [0, 0, 2, 0, 2, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-455": [0, 0, 4, 0, 4, 4, "fs4-20", "4 Channel 4/20mA Input"],
    "750-456": [0, 0, 2, 0, 2, 2, "fs10", "2 Channel +-10V Differential Input"],
    "750-457": [0, 0, 4, 0, 4, 4, "fs10", "4 Channel +-10V Input"],
    "750-459": [0, 0, 4, 0, 4, 4, "fs10", "4 Channel Channel 0/10V Input"],
    "750-461": [0, 0, 2, 0, 2, 2, "thc", "2 Channel PT100 Input"],
    "750-462": [0, 0, 2, 0, 2, 2, "thc", "2 Channel Thermocouple Input"],
    "750-465": [0, 0, 2, 0, 2, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-466": [0, 0, 2, 0, 2, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-467": [0, 0, 2, 0, 2, 2, "fs10", "2 Channel 0/10V Input"],
    "750-468": [0, 0, 4, 0, 4, 4, "fs10", "4 Channel 0/10V Input"],
    "750-469": [0, 0, 2, 0, 2, 2, "thc", "2 Channel Ktype Thermocouple Input"],
    "750-472": [0, 0, 2, 0, 2, 2, "fs20", "2 Channel 0/20mA 16bit Input"],
    "750-474": [0, 0, 2, 0, 2, 2, "fs4-20", "2 Channel 4/20mA 16bit Input"],
    "750-476": [0, 0, 2, 0, 2, 2, "fs10", "2 Channel +-10V Input"],
    "750-477": [0, 0, 2, 0, 2, 2, "fs20", "2 Channel 0/10V Differential Input"],
    "750-478": [0, 0, 2, 0, 2, 2, "fs10", "2 Channel 0/10V Input"],
    "750-479": [0, 0, 2, 0, 2, 2, "fs10", "2 Channel +-10V Input"],
    "750-480": [0, 0, 2, 0, 2, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-483": [0, 0, 2, 0, 2, 2, "fs30", "2 Channel 0/30V Differential Input"],
    "750-485": [0, 0, 2, 0, 2, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-492": [0, 0, 2, 0, 2, 2, "fs4-20", "2 Channel 4/20mA Differential Input"],
    "750-501": [0, 2, 0, 0, 2, 2, "digital", "2 Channel Digital Output"],
    "750-502": [0, 2, 0, 0, 2, 2, "digital", "2 Channel Digital Output"],
    "750-504": [0, 4, 0, 0, 4, 4, "digital", "4 Channel Digital Output"],
    # Input process image has 2 diagnostic bits x channel
    # Output process image has 4 bits, first two are control bits, latest are not used
    "750-506": [4, 4, 0, 0, 2, 6, "digital", "2 Channel Digital Output"],  # special
    # Input process image has 1 diagnostic bit x channel
    # Output process image has 1 control bit x channel
    "750-507": [2, 2, 0, 0, 2, 4, "digital", "2 Channel Digital Output"],  # special
    # Input process image has 1 diagnostic bit x channel
    # Output process image has 1 control bit x channel
    "750-508": [2, 2, 0, 0, 2, 4, "digital", "2 Channel Digital Output"],  # special
    "750-509": [0, 2, 0, 0, 2, 2, "digital", "2 Channel Digital Output"],
    "750-512": [0, 2, 0, 0, 2, 2, "digital", "2 Normally Open Relay Output"],
    "750-513": [0, 2, 0, 0, 2, 2, "digital", "2 Normally Open Relay Output"],
    "750-514": [0, 2, 0, 0, 2, 2, "digital", "2 Changeover Relay Output"],
    "750-516": [0, 4, 0, 0, 4, 4, "digital", "4 Channel Digital Output"],
    "750-517": [0, 2, 0, 0, 2, 2, "digital", "2 Changeover Relay Output"],
    "750-519": [0, 4, 0, 0, 4, 4, "digital", "4 Channel Digital Output"],
    "750-530": [0, 8, 0, 0, 8, 8, "digital", "8 Channel Digital Output"],
    "750-531": [0, 4, 0, 0, 4, 4, "digital", "4 Channel Digital Output"],
    "750-536": [0, 8, 0, 0, 8, 8, "digital", "8 Channel Digital Output"],
    "750-550": [0, 0, 0, 2, 2, 2, "fs10", "2 Channel 0/10V Output"],
    "750-552": [0, 0, 0, 2, 2, 2, "fs20", "2 Channel 0/20mA Output"],
    "750-554": [0, 0, 0, 2, 2, 2, "fs4-20", "2 Channel 4/20mA Output"],
    "750-556": [0, 0, 0, 2, 2, 2, "fs10", "2 Channel +-10V Output"],
    "750-557": [0, 0, 0, 4, 4, 4, "fs10", "4 Channel +-10V Output"],
    "750-562": [0, 0, 0, 2, 2, 2, "fs10", "2 Channel +-10V 16bit Output"],
    "750-562-UP": [0, 0, 0, 2, 2, 2, "fs10", "2 Channel 0/10V 16bit Output"],
    "750-630": [0, 0, 2, 0, 1, 1, "ssi24", "24 bit SSI encoder"],
    "750-630-24": [0, 0, 2, 0, 1, 1, "ssi24", "24 bit SSI encoder"],
    "750-630-32": [0, 0, 2, 0, 1, 1, "ssi32", "32 bit SSI encoder"],
    # Both Input and Output process images has 1 Control/Status
    # byte of Channel 1 in the first word (and an empty byte)
    # the second word has the Data value of the channel
    "750-637": [0, 0, 4, 4, 2, 8, "637", "32 bit Incremental encoder"],  # special
    "750-653": [0, 0, 2, 2, 1, 1, "653", "RS485 Serial Interface"],  # special
    "750-1416": [8, 0, 0, 0, 8, 8, "digital", "8 Channel Digital Input"],
    "750-1417": [8, 0, 0, 0, 8, 8, "digital", "8 Channel Digital Input"],
    "750-1515": [0, 8, 0, 0, 8, 8, "digital", "8 Channel Digital Output"],
}


# go through catalogue entries and change it to a NamedTuple

for module_name, module_info in MODULES_CONFIG.items():
    reading_info = {}
    writing_info = {}

    MODULES_CONFIG[module_name] = ModConf(*module_info, reading_info, writing_info)


@functools.lru_cache()
def get_channel_info(module_name, module_channel=0, extended_mode=False):

    module_info = MODULES_CONFIG[module_name]

    reading_type = module_info.reading_type

    info = module_info.reading_info
    info["reading_type"] = module_info.reading_type
    if module_name == "750-404":
        if extended_mode:
            # counter_value, counter_status, counter_setting_value, counter_control = (
            if module_channel in (0, 2):
                info["bits"] = 32
            elif module_channel in (1, 3):
                info["bits"] = 8
            if module_channel in (0, 1):
                info["type"] = "ANA_IN"
            elif module_channel in (2, 3):
                info["type"] = "ANA_OUT"
        else:
            # counter_status, counter_value
            if module_channel == 0:
                info["bits"] = 8
                info["type"] = "ANA_IN"
            elif module_channel == 1:
                info["bits"] = 32
                info["type"] = "ANA_IN"

    elif module_name in ("750-637",):
        if extended_mode:
            # a_val, a_status, b_val, b_status, a_set_val, a_control, b_set_val, b_control = (
            if module_channel in (1, 3, 5, 7):
                info["bits"] = 8
            elif module_channel in (0, 2, 4, 6):
                info["bits"] = 32
            else:
                raise RuntimeError(
                    f"Module channel n.{module_channel} not available for the Wago module {module_name} with extended_mode={extended_mode}"
                )
            if module_channel in (0, 1, 2, 3):
                info["type"] = "ANA_IN"
            elif module_channel in (4, 5, 6, 7):
                info["type"] = "ANA_OUT"
        else:
            if module_channel in (0, 1):
                info["bits"] = 32
                info["type"] = "ANA_IN"

    elif reading_type.startswith("fs"):
        info["reading_type"] = "fs"
        info["bits"] = 16
        info["type"] = "ANA_IN"
        try:
            fs_low, fs_high = map(int, reading_type[2:].split("-"))
        except ValueError:
            fs_low = 0
            fs_high = int(reading_type[2:])
        else:
            if fs_low != 0:
                fs_high -= fs_low

        info["low"] = fs_low
        info["high"] = fs_high
        if module_name.endswith("477"):
            info["base"] = 20000
        elif module_name.endswith("562-UP"):
            info["base"] = 65535
        else:
            info["base"] = 32767
    elif reading_type.startswith("ssi"):
        info["reading_type"] = "ssi"
        info["type"] = "ANA_IN"
        info["bits"] = int(reading_type[3:])
    elif reading_type in ("counter", "637"):
        info["reading_type"] = "counter"
        info["bits"] = 32
    elif reading_type.startswith("thc"):
        info["reading_type"] = "thc"
        info["bits"] = 16
        info["type"] = "ANA_IN"
    elif reading_type == "digital":
        info["reading_type"] = "digital"
        info["bits"] = 1
        total_ch = module_info.digi_out + module_info.digi_in
        # in case of special modules first we map digital out
        if module_channel in range(0, module_info.digi_out):
            info["type"] = "DIGI_OUT"
        elif module_channel in range(module_info.digi_out, total_ch):
            info["type"] = "DIGI_IN"
    else:
        raise RuntimeError(f"Can't retrieve information on {module_name}")

    try:
        # those should be always defined
        info["type"]
        info["bits"]
    except KeyError:
        raise KeyError(
            f"Module channel n.{module_channel} not available for the Wago module {module_name} with extended_mode={extended_mode}"
        )

    return module_info


get_module_info = get_channel_info


def get_wago_comm(conf):
    """Return comm instance, unique for a particular host"""

    comm = get_comm(conf)  # this will only setup, not connect
    with gevent.Timeout(3):
        host = comm.host
        port = comm.port
        fqdn = socket.getfqdn(host)

    try:
        singleton = WAGO_COMMS[f"{fqdn}:{port}"]
    except KeyError:
        singleton = comm
        WAGO_COMMS[f"{fqdn}:{port}"] = singleton

    return comm


class TangoWago:
    def __init__(self, comm, modules_config):
        """
        Bridge beetween Wago `user` class and
        a tango Device Server
        """
        self.comm = comm
        self.modules_config = modules_config

        global_map.register(self, tag=f"TangoEngine", children_list=[self.comm])

    def get(self, *args, **kwargs):
        log_debug(self, f"In get args={args} kwargs={kwargs}")
        values = []
        for name in args:
            key = self.modules_config.devname2key(name)
            val = self.comm.command_inout("DevReadNoCachePhys", key)
            values.append(val)

        values = flatten(values)

        if not values:
            return None

        if len(values) == 1:
            return values[0]

        return values

    def connect(self):
        """Added for compatibility"""
        log_debug(self, "In connect")

    def close(self):
        """Added for compatibility"""
        log_debug(self, "In close")

    def set(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        log_debug(self, f"In set args={args}")
        array = self.modules_config._resolve_write(*args)

        for write_operation in array:
            self.comm.command_inout("devwritephys", write_operation)

    def __getattr__(self, attr):
        if attr.startswith("dev") or attr in ("status", "state"):
            return getattr(self.comm, attr)
        else:
            raise AttributeError


class ModulesConfig:
    def __init__(
        self,
        mapping_str,
        main_module="750-842",
        ignore_missing=False,
        extended_mode=False,
    ):
        """Various helper methods to manage the modules configuration for the
        Wago PLC

        Args:
            mapping_str (str): a comma separated string containing the vendor code
                               for the module followed by names of logical channels

        Example:
            750-478,inclino,rien
            750-469,thbs1,thbs2
            750-469,thbs3,thbs4
            750-469,thbs5,thbs6
            750-469,thbs7,thbs8
            750-469,thbs9,thbs10
            750-469,bstc1, bstc2
            750-469,coltc1,coltc2
            750-517,intlckcol,intlckinc
        """
        self.__extended_mode = extended_mode

        self.mapping_str = mapping_str
        self.__mapping = []
        self.__modules = [main_module]  # first element is the Ethernet Module

        for module_name, channels in ModulesConfig.parse_mapping_str(mapping_str):
            if module_name not in MODULES_CONFIG:
                raise RuntimeError("Unknown module: %r" % module_name)
            if module_name in ("750-653",):
                raise NotImplementedError

            # check n. of channels
            if extended_mode:
                n_channels = get_channel_info(module_name).n_channels_ext
            else:
                n_channels = get_channel_info(module_name).n_channels

            if not ignore_missing and len(channels) != n_channels:
                raise RuntimeError(
                    f"Mapping of channels on module {module_name} is not correct"
                )

            self.__modules.append(module_name)

            self.__mapping.append({"module": module_name, "channels": channels})

        self.create_memory_table()
        self.create_read_table()

    @property
    def extended_mode(self):
        return self.__extended_mode

    def create_memory_table(self):
        """This will give a representation of the wago memory and
        where the logical_devices/channels are mapped

        Returns:
            dict: 4 string keys (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT), every
            one contains a list of tuples that contains
                (logical_name: str, logical_channel: int, module_name: str,
                 physical_module_number, physical_module_channel )
            of a logical device.

            The important fact is that this reflects the Wago memory, so, for example
            the third element of ANA_IN is the third Word in Wago modbus memory area,
            this is needed as a helper for manipulating.
            We can have empty channels if the user does not assign names, in this case
            we will have a None value instead.

        Example:
            >>> # asking for information about the first word mapped to
            >>> # the Analog Input area
            >>> self.memory_table['ANA_IN'][0]
            DeviceInfo(logical_device='encpsb', logical_channel=0, module_name='750-630', physical_module_number=2, physical_module_channel=0, info=ModConf(digi_in=0, digi_out=0, ana_in=2, ana_out=0, n_channels=1, n_channels_ext=1, reading_type='ssi24', description='24 bit SSI encoder', reading_info={'reading_type': 'ssi', 'type': 'ANA_IN', 'bits': 24}, writing_info={}))

            >>> # we know that this memory area is connected to the first channel
            >>> # (channel 0) of a logical device called 'temp_tr1' 
            >>> # we also know that the PLC module is the first one attached
            >>> # to the Main Wago Cpu and also this is the first input of the module
            """
        memory = {"DIGI_IN": [], "DIGI_OUT": [], "ANA_IN": [], "ANA_OUT": []}
        device_map = dict()

        for phys_mod_num, (module_name, logical_devices) in enumerate(
            ModulesConfig.parse_mapping_str(self.mapping_str)
        ):
            # Example of calling ModulesConfig.parse_mapping_str
            #
            # [('750-504', ['foh2ctrl', 'foh2ctrl', 'foh2ctrl', 'foh2ctrl']),
            # ('750-408', ['foh2pos', 'sain2', 'foh2pos', 'sain4']),
            # ('750-408', ['foh2pos', 'sain6', 'foh2pos', 'sain8']), ...
            # populate channels_map
            device_memory = []  # mapped memory for a device

            module_info = get_channel_info(module_name)

            for phys_chan_num, logical_device in enumerate(logical_devices):
                # Example: 0, 'foh2ctrl'
                if logical_device in device_map:
                    device_map[logical_device] += 1
                else:
                    device_map[logical_device] = 0

                channel = device_map[logical_device]
                # E.G. ('esTf1', 0, 469, 0, 0)

                # extracting the module type as integer E.G."750-469" -> 469
                # module_reference = int(module_name.split("-")[1])

                devinfo = collections.namedtuple(
                    "DeviceInfo",
                    (
                        "logical_device",
                        "logical_channel",
                        "module_name",
                        "physical_module_number",
                        "physical_module_channel",
                        "info",
                    ),
                )

                device_memory.append(
                    devinfo(
                        logical_device,
                        channel,
                        module_name,
                        phys_mod_num,
                        phys_chan_num,
                        get_channel_info(
                            module_name,
                            phys_chan_num,
                            extended_mode=self.__extended_mode,
                        ),
                    )
                )

            # fill eventually missing channels (ignore_missing = True)
            filled_channels = device_memory + [None] * (
                module_info.n_channels_ext - len(device_memory)
            )

            # now filled_channels is a list of DeviceInfo named tuples
            #
            # Example
            # [DeviceInfo(logical_device='foh2ctrl', logical_channel=0, module_name='750-504', physical_module_number=0, physical_module_channel=0),
            # DeviceInfo(logical_device='foh2ctrl', logical_channel=1, module_name='750-504', physical_module_number=0, physical_module_channel=1), ...

            if module_name == "750-404":  # 32 bit counter
                # Input process image has 2 words of counter value and 1 byte of status,
                # total of 3 words
                # Output process image has 2 words of counter setting value and 1 byte of
                # control, total of 3 words
                if self.__extended_mode:
                    counter_value, counter_status, counter_setting_value, counter_control = (
                        filled_channels
                    )
                    memory["ANA_IN"].extend(
                        [counter_status, counter_value, counter_value]
                    )
                    memory["ANA_OUT"].extend(
                        [counter_control, counter_setting_value, counter_setting_value]
                    )

                else:
                    counter_status, counter_value, *_ = filled_channels

                    memory["ANA_IN"].extend(
                        [counter_status, counter_value, counter_value]
                    )
                    memory["ANA_OUT"].extend([None, None, None])

            elif module_name == "750-637":
                # Both Input and Output process images has 1 Control/Status
                # byte of Channel 1 in the first word (and an empty byte)
                # the second word has the Data value of the channel

                if self.__extended_mode:
                    a_val, a_status, b_val, b_status, a_set_val, a_control, b_set_val, b_control = (
                        filled_channels
                    )
                    memory["ANA_IN"].extend([a_status, a_val, b_status, b_val])
                    memory["ANA_OUT"].extend(
                        [a_control, a_set_val, b_control, b_set_val]
                    )
                else:
                    # Replicating C++ code for this device
                    # maps on the first logical_channel
                    # status bits:
                    #     logical channel 0
                    #     00C100C0  (32 bits signed)
                    # and on the second logical_channel
                    # values
                    #     logical channel 1
                    #     D3D2D1D0  (32 bit signed)

                    status, value, *_ = filled_channels

                    memory["ANA_IN"].extend([status, value, status, value])
                    memory["ANA_OUT"].extend([None, None, None, None])

            elif module_info.reading_type.startswith("ssi"):
                for ch in filled_channels:
                    # encoders occupy two words
                    memory["ANA_IN"].extend([ch])
                    memory["ANA_IN"].extend([ch])

            elif module_info.reading_type == "digital":
                if module_info.digi_in > 0 and module_info.digi_out > 0:
                    # we have both digital input and outputs
                    # we normally map only the outputs, but in extended mode
                    # we map first outputs that inputs
                    if self.__extended_mode:
                        ch_digi_out = filled_channels[: module_info.digi_out]
                        ch_digi_in = filled_channels[module_info.digi_out :]
                        for ch in ch_digi_out:
                            memory["DIGI_OUT"].append(ch)
                        for ch in ch_digi_in:
                            memory["DIGI_IN"].append(ch)
                    else:
                        memory["DIGI_IN"].extend([None] * module_info.digi_in)
                        for ch in filled_channels[: module_info.digi_out]:
                            memory["DIGI_OUT"].append(ch)

                elif module_info.digi_in > 0:
                    memory["DIGI_IN"].extend(filled_channels)
                elif module_info.digi_out > 0:
                    memory["DIGI_OUT"].extend(filled_channels)
            elif module_info.ana_in > 0:
                memory["ANA_IN"].extend(filled_channels)
            elif module_info.ana_out > 0:
                memory["ANA_OUT"].extend(filled_channels)
            else:
                raise NotImplementedError
        self.memory_table = memory

    def create_read_table(self):
        """
        Creates a read table with informations about modules and memory mapping connected
        to a logical_device_name

        Examples:

        >>> self.read_table.keys()  # get all logical_device_names
        dict_keys(['foh2pos', 'sain2', 'sain4', 'sain6', 'sain8', 'pres', ... ])

        >>> self.read_table['foh2pos'].keys()  # get all logical_channels
        dict_keys([0, 1, 2, 3])

        >>> len(self.read_table['foh2pos'].keys())  # how many channels

        >>> self.read_table['foh2pos'][1]
        {'module_reference': '750-408', 'info': ModConfig(...) ,'DIGI_IN': {'mem_position': [2]}}
        >>> # channel 1 of foh2pos is a DIGI_IN and is you can read it in the
        >>> # memory position n.2 of DIGI_IN area
        """
        log_dev_tree = dict()

        types = "DIGI_IN DIGI_OUT ANA_IN ANA_OUT".split()
        for type_ in types:
            for mem_position, (mem_info) in enumerate(self.memory_table[type_]):
                if mem_info is None:  # not mapped channel
                    continue
                logical_device = mem_info.logical_device
                logical_channel = mem_info.logical_channel
                module_reference = mem_info.module_name
                info = mem_info.info
                if logical_device not in log_dev_tree:
                    log_dev_tree[logical_device] = {
                        logical_channel: {
                            "module_reference": module_reference,
                            "info": info,
                        }
                    }
                if logical_channel not in log_dev_tree[logical_device]:
                    log_dev_tree[logical_device][logical_channel] = {
                        "module_reference": module_reference,
                        "info": info,
                    }

                if type_ not in log_dev_tree[logical_device][logical_channel]:
                    log_dev_tree[logical_device][logical_channel][type_] = {
                        "mem_position": []
                    }

                log_dev_tree[logical_device][logical_channel][type_][
                    "mem_position"
                ].append(mem_position)

        self.read_table = log_dev_tree

    @property
    def mapping(self):
        return self.__mapping

    @property
    def modules(self):
        """Returns all vendor modules of PLC
        the information is taken from the given mapping

        Example:
            >>> wago.modules
            ['750-842', '750-430', '740-456']
        """
        return self.__modules

    @property
    def attached_modules(self):
        """Returns all attached modules of PLC (excluding CPU module)
        the information is taken from the given mapping
        Example:
            >>> wago.modules
            ['750-430', '740-456']
        """
        return self.__modules[1:]

    @staticmethod
    def parse_mapping_str(mapping_str: str):
        """
        Parse a configuration string and yields plc module information

        args:
            mapping_str: string containing PLC's attached modules info

        Returns:
                module_name, list of channels

        Example:
            750-478,inclino,rien
            750-469,thbs1,thbs2
            750-469,thbs3,thbs4
            750-469,thbs5,thbs6

            first yield gives 750-478, ["inclino", "rien"]
            second yield gives 750-469, ["thbs1", "thbs2"]
        """

        for _line in splitlines(mapping_str):
            line = _line.replace(":", ",")
            items = [item.strip() for item in [_f for _f in line.split(",")]]  # if _f]]
            # items = [item.strip() for item in [_f for _f in line.split(",") if _f]]
            if items:
                module_name, channels = items[0], items[1:]
                for channel in channels:
                    # an empty channel name cannot be followed by non empty
                    # channel names
                    if bool(channel) is False:
                        raise RuntimeError(
                            f"You have to specify channel name at line:{_line}"
                        )
                if module_name:
                    yield module_name, channels

    @classmethod
    def from_config_tree(cls, config_tree: dict):
        """Alternative constructor with config_tree"""

        ignore_missing = config_tree.get("ignore_missing", False)
        mapping = []

        if config_tree.get("mapping"):
            for module in config_tree["mapping"]:
                module_type = module["type"]
                logical_names = module["logical_names"]
                mapping.append("%s,%s" % (module_type, logical_names))
        extended_mode = config_tree.get("extended_mode", False)

        return cls(
            "\n".join(mapping),
            ignore_missing=ignore_missing,
            extended_mode=extended_mode,
        )

    @classmethod
    def from_tango_config(cls, config: dict):
        """Alternative constructor with Wago Device Server 
        config property"""

        return cls("\n".join(config), ignore_missing=True)

    def update_cpu(self, module: str):
        """Updates information about the CPU module
        I.E. 750-842, 750-891
        """
        if module in MODULES_CONFIG and MODULES_CONFIG[module][READING_TYPE] == "cpu":
            self.__modules[0] == module
        else:
            raise RuntimeError("Not known CPU module")

    def devkey2name(self, key):
        """
        From a key (channel enumeration) to the assigned text name

        Example:
            >>> DevKey2Name(3)
            b"gabsTf3"
        """
        try:
            inv_map = {v: k for k, v in self.logical_keys.items()}
            return inv_map[key]
        except IndexError:
            raise Exception("invalid logical channel key")

    def devname2key(self, name):
        """
        From the name of a channel to the given key"""
        return self.logical_keys[name]

    def devhard2log(self, array_in):
        """
        Given some information about the position of a register in Wago memory
        it returns the corresponding logical device key and logical channel

        Args:
            channel_type: gives information about input/output type
                          the Most significant byte is either ord('I') for input
                          or ord('O') for Output
                          Least significant byte is either ord('B') for Bit (digital)
                          or ord('W') for Word (analog)

            offset: offset in wago memory, this means that the first digital output
                    will be offset 0, the second digital output will be 1 and so on.
                    If we have an analog output following the digital one the offset
                    starts again from zero.

        Returns: (logical_device_key, logical_device_channel)
        """
        channel_type, offset = array_in

        # the following will check type/convert, raising if wrong
        channel_type = register_type_to_int(channel_type)

        if channel_type == 18754:
            info = self.memory_table["DIGI_IN"]
        elif channel_type == 20290:
            info = self.memory_table["DIGI_OUT"]

        elif channel_type == 18775:
            info = self.memory_table["ANA_IN"]

        elif channel_type == 20311:
            info = self.memory_table["ANA_OUT"]
        else:
            raise RuntimeError("Invalid channel type")

        try:
            # can be None
            logical_device = info[offset].logical_device
            logical_channel = info[offset].logical_channel

        except (IndexError, AttributeError):
            raise RuntimeError("Invalid offset")

        logical_device_key = self.devname2key(logical_device)
        return logical_device_key, logical_channel

    def devlog2hard(self, array_in):

        device_key, logical_channel = array_in
        logical_device = self.devkey2name(device_key)
        for offset, el in enumerate(self.memory_table["DIGI_IN"]):
            channel_base_address = 18754
            if el is not None:
                if el[0] == logical_device and el[1] == logical_channel:
                    module_name = el.module_name
                    phys_mod_num = el.physical_module_number
                    phys_chan_num = el.physical_module_channel

                    module_reference = int(module_name.split("-")[1])
                    return (
                        offset,
                        channel_base_address,
                        module_reference,
                        phys_mod_num,
                        phys_chan_num,
                    )
        for offset, el in enumerate(self.memory_table["DIGI_OUT"]):
            channel_base_address = 20290
            if el is not None:
                if el[0] == logical_device and el[1] == logical_channel:
                    module_name = el.module_name
                    phys_mod_num = el.physical_module_number
                    phys_chan_num = el.physical_module_channel

                    module_reference = int(module_name.split("-")[1])
                    return (
                        offset,
                        channel_base_address,
                        module_reference,
                        phys_mod_num,
                        phys_chan_num,
                    )
        for offset, el in enumerate(self.memory_table["ANA_IN"]):
            channel_base_address = 18775
            if el is not None:
                if el[0] == logical_device and el[1] == logical_channel:
                    module_name = el.module_name
                    phys_mod_num = el.physical_module_number
                    phys_chan_num = el.physical_module_channel

                    module_reference = int(module_name.split("-")[1])
                    return (
                        offset,
                        channel_base_address,
                        module_reference,
                        phys_mod_num,
                        phys_chan_num,
                    )
        for offset, el in enumerate(self.memory_table["ANA_OUT"]):
            channel_base_address = 20311
            if el is not None:
                if el[0] == logical_device and el[1] == logical_channel:
                    module_name = el.module_name
                    phys_mod_num = el.physical_module_number
                    phys_chan_num = el.physical_module_channel

                    module_reference = int(module_name.split("-")[1])
                    return (
                        offset,
                        channel_base_address,
                        module_reference,
                        phys_mod_num,
                        phys_chan_num,
                    )
        raise RuntimeError("invalid logical channel Key")

    def devlog2scale(self, array_in):
        raise NotImplementedError

    def keys(self):
        return self.logical_keys.values()

    def _resolve_write(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        Args:
            list or pairs:  channel_name, value
                            or a list with channel_name, val1, val2, ..., valn
                            or a combination of the two

        Returns:
            list of lists: [[logical_device_key1, logical_channel1, value1, logical_channel2, value2], [logical_device_key2, logical_channel1, value1], ...]
            This list is well suited to be used with DevWritePhys
        """
        log_debug(self, f"In set args={args}")

        channels_to_write = []
        current_list = channels_to_write
        for x in args:
            if type(x) in (bytes, str):
                # channel name
                current_list = [str(x)]
                channels_to_write.append(current_list)
            else:
                # value
                current_list.append(x)

        for i in range(len(channels_to_write)):
            x = channels_to_write[i]
            if len(x) > 2:
                # group values for channel with same name
                # in a list
                channels_to_write[i] = [x[0], x[1:]]

        out_array = []
        for logical_device, *values in channels_to_write:
            logical_device_key = self.devname2key(logical_device)

            key_array = [logical_device_key]

            real_channels = self.read_table[
                logical_device
            ].keys()  # real number of channels
            for channel, val in enumerate(flatten(values)):
                # trying to get the channel, if this does not exists
                # the following will raises IndexError
                if channel not in real_channels:
                    raise KeyError(f"Channel(s) '{channel}` doesn't exist in Mapping")
                key_array.extend([channel, val])
            if (len(real_channels) * 2) + 1 != len(key_array):
                raise RuntimeError(
                    f"Cannot write: expected n. {len(real_channels)} values for logical device {logical_device}"
                )

            out_array.append(key_array)
            # logical_device_key, than pairs of channel,values
        return out_array

    @property
    def logical_keys(self):
        """
        Returns:
            dict: key is 'logical name'(str), value is logical key(int)

        Example:
            {'pot1vol': 0, 'pot1cur': 1, 'pot2vol': 2, 'pot2cur': 3, 'adc5': 4, 'adc6': 5, 'pot1out': 6, ...}
        """
        try:
            self.__logical_keys
        except AttributeError:
            key = 0
            registered_channels = []
            mapping_ = {}
            for module_name, channels in ModulesConfig.parse_mapping_str(
                self.mapping_str
            ):
                for channel in channels:
                    if channel not in registered_channels:
                        mapping_[channel] = key
                        registered_channels.append(channel)
                        key += 1
            self.__logical_keys = mapping_
        return self.__logical_keys

    @property
    def bit_output_mem_area(self):
        """Returns the address of the first Word in plc Wago Memory
        where digital outputs are mapped

        Normally in Wago memory at first all analog outputs
        are mapped starting on %QW0 up to the needed quantity,
        than digital outputs are mapped one output per bit
        starting from the LSB of the Word
        """
        return len(self.memory_table["ANA_OUT"])


class MissingFirmware(RuntimeError):
    pass


class WagoController:
    """
    The wago controller class
    """

    def __init__(
        self, comm, modules_config: ModulesConfig, timeout=1.0, polling_time=2
    ):
        log_debug(self, "In __init__")
        self.client = comm
        self.timeout = timeout
        self.modules_config = modules_config

        # setting up polling
        self.polling_time = polling_time
        self.last_read = 0

        self.series, self.order_nu = 0, 0
        self.firmware = {"date": "", "version": 0, "time": ""}

        self.coupler = False

        self.lock = gevent.lock.Semaphore()
        global_map.register(self, tag=f"Engine", children_list=[comm])

    def connect(self):
        """ Connect to the wago. Check if we have a coupler or a controller.
        In case of controller get the firmware version and firmware date.
        """
        log_debug(self, "In connect")
        try:
            # check if we have a coupler or a controller
            self.series = self.client_read_input_registers(0x2011, "H")
        except Exception:
            log_error(self, "Error connecting to Wago")
            raise

        self.order_nu = self.client_read_input_registers(0x2012, "H")

        self.modules_config.update_cpu(f"750-{self.order_nu}")

        self.coupler = self.order_nu < 800
        if not self.coupler:
            # get firmware date and version
            reply = self.client_read_input_registers(0x2010, "H")
            self.firmware["version"] = reply
            reply = struct.pack("8H", *self.client.read_input_registers(0x2022, "8H"))
            self.firmware["date"] = "/".join(
                (x.decode("utf-8") for x in reply.split(b"\x00") if x)
            )
            reply = struct.pack("8H", *self.client_read_input_registers(0x2021, "8H"))
            self.firmware["time"] = "/".join(
                (x.decode("utf-8") for x in reply.split(b"\x00") if x)
            )
        self.__check_plugged_modules()

    def close(self):
        """
        Close the connection.
        """
        log_debug(self, "In close")
        with self.lock:
            self.client.close()

    def _read_fs(self, raw_value, **kwargs):
        """Read Digital Input type module. Make full scale conversion.
        """
        low = kwargs.get("low", 0)
        high = kwargs.get("high", 10)
        base = kwargs.get("base", 32767)
        value = ctypes.c_short(raw_value).value
        return (value * high / float(base)) + low

    def _read_ssi(self, raw_value, **kwargs):
        """Read SSI (absolute encoders) type module
        Returns:
            (float): 24 bits precision, signed float
        """
        bits = kwargs.get("bits", 24)
        # reading is two words, 16 bits each
        value = raw_value[0] + raw_value[1] * (1 << 16)
        return float(to_signed(value, bits=bits))

    def _read_thc(self, raw_value, **kwargs):
        """Read a thermocouple type module.
        Returns:
            (float): signed float
        """
        bits = kwargs.get("bits", 16)
        value = ctypes.c_ushort(raw_value).value
        return to_signed(value, bits=bits) / 10

    def update_read_table(self):
        """Reads input/output modules and updates a cached table
        `self.value_table` that is a dictionary with 4 keys
        - "DIGI_IN"
        - "DIGI_OUT"
        - "ANA_IN"
        - "ANA_OUT"

        Every key gives an array that corresponds to the memory area
        in the Wago.

        Those values are than used by `get` to give back values to
        the user.
        This can be extended to implement a cache.

        Example:
            {'DIGI_IN': array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0], dtype=uint8), 
            'DIGI_OUT': array([0, 0, 0, 0, 0, 1, 1, 1, 0, 0], dtype=uint8), 
            'ANA_IN': (55809, 60774, 53568, 60630, 28176, 3948, 64595, 
            37649, 23242, 33207), 
            'ANA_OUT': (29109, 49427)}
        """

        self.value_table = {}
        memory = self.modules_config.memory_table
        total_digi_in = len(memory["DIGI_IN"])
        total_digi_out = len(memory["DIGI_OUT"])
        total_ana_in = len(memory["ANA_IN"])
        total_ana_out = len(memory["ANA_OUT"])

        if total_digi_in > 0:
            digi_in_reading = self.client_read_coils(0, total_digi_in)
            self.value_table["DIGI_IN"] = digi_in_reading

        if total_digi_out > 0:
            digi_out_reading = self.client_read_coils(0x200, total_digi_out)
            self.value_table["DIGI_OUT"] = digi_out_reading

        if total_ana_in > 0:
            ana_in_reading = self.client_read_input_registers(0, total_ana_in * "H")
            self.value_table["ANA_IN"] = ana_in_reading

        if total_ana_out > 0:
            ana_out_reading = self.client_read_input_registers(
                0x200, total_ana_out * "H"
            )
            self.value_table["ANA_OUT"] = ana_out_reading

    def get(self, *logical_names, convert_values=True, flat=True, cached=False):

        if not cached or (time.time() - self.last_read) > self.polling_time:
            self.update_read_table()
            self.last_read = time.time()

        result = []
        for name in logical_names:

            values_group_by_logical_name = []
            channels_to_read = self.modules_config.read_table[name].keys()
            for chann in channels_to_read:
                value = []  # normally is a single value, with encoder could be two values
                channel_info = self.modules_config.read_table[name][chann]["info"]
                reading_info = channel_info.reading_info
                types = [
                    t
                    for t in self.modules_config.read_table[name][chann].keys()
                    if t in ("DIGI_IN", "DIGI_OUT", "ANA_IN", "ANA_OUT")
                ]

                for type_ in types:
                    for mem_pos in self.modules_config.read_table[name][chann][type_][
                        "mem_position"
                    ]:
                        value.append(self.value_table[type_][mem_pos])
                # at this point value can be either [v] or [v1,v2] (encoders)
                if convert_values:  # encoder has always to be joined in one
                    v = self._read_values(value, reading_info)
                else:
                    v = value[0]
                values_group_by_logical_name.append(v)  # gives already a list

            if len(values_group_by_logical_name) == 1:
                # if only one value do not use a list
                values_group_by_logical_name = values_group_by_logical_name[0]
            result.append(values_group_by_logical_name)  # list of lists

        if not flat:
            result = flatten(result)
            ret = []
            for name in logical_names:
                self.modules_config.read_table[name]
                nval = len(self.modules_config.read_table[name].keys())
                if nval > 1:
                    channel_values, result = result[:nval], result[nval:]
                else:
                    channel_values = result.pop(0)
                ret.append(channel_values)
            return ret

        # return a list with all the channels
        if not result:
            return None

        if len(result) == 1:
            return result[0]

        # ret represents a list of lists, containing Wago values
        # by Wago module, but we prefer to have a flat list
        return flatten(result)

    def _write_ssi(self, value, **kwargs):
        raw_values = []
        bits = kwargs.get("bits", 24)
        value = to_unsigned(value, bits=bits)
        while bits > 0:
            bits -= 16
            raw_values.append(value & 0xffff)
        return raw_values

    def _write_fs(self, value, **kwargs):
        low = kwargs.get("low", 0)
        high = kwargs.get("high", 10)
        base = kwargs.get("base", 32767)
        return int(((value - low) * base / float(high))) & 0xffff

    def _read_values(self, raw_values, channel_info):
        reading_type = channel_info["reading_type"]
        bits = channel_info["bits"]

        if reading_type in ("fs",):
            return self._read_fs(raw_values[0], **channel_info)

        if reading_type in ("thc",):
            return self._read_thc(raw_values[0], **channel_info)

        if bits > 1:  # not a digital channel
            # transform to signed value
            # this is to manage ssi, counters and status words that has
            # different bits size
            return self._read_ssi(raw_values, **channel_info)
        if len(raw_values) > 1:
            raise NotImplementedError

        return raw_values[0]

    def set(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        log_debug(self, f"In set args={args}")
        array = self.modules_config._resolve_write(*args)

        for write_operation in array:
            self.devwritephys(write_operation)

    def devwritephys(self, array_in):
        """Writes one or more values to the PLC

        array_in:
                  - first number is logical device
                  - than pairs of logical channels and value to write
        Example:
            devwritephys(0, 0, 3.2, 1, 7.4)
            # will write to logical device 0
            # value 3.2 on logical channel 0 (of logical device 0)
            # value 7.4 on logical channel 1 (of logical device 0)
        """

        # this is a standalone implementation of writing value
        # that differs from `set` and is more suitable for a low
        # level writing of only some values

        array = [el for el in array_in]  # just copy it to later manipulate
        key = int(array.pop(0))
        name = self.devkey2name(key)
        while array:
            ch, val, array = int(array[0]), array[1], array[2:]

            """
            [0] : offset in wago controller memory (ex: 0x16)
            [1] : MSB=I/O LSB=Bit/Word (ex: 0x4957 = ('I'<<8)+'W')
            [2] : module reference (ex: 469)
            [3] : module number (1st is 0)
            [4] : physical channel of the module (ex: 1 for the 2nd)
            """
            offset, register_type, _, _, _ = self.devlog2hard((key, ch))
            size = len(self.modules_config.read_table[name])
            module_reference = self.modules_config.read_table[name][ch][
                "module_reference"
            ]
            module_info = get_channel_info(module_reference)

            if register_type == register_type_to_int("OB"):
                # output bit
                self.client_write_coil(offset, bool(val), timeout=self.timeout)
            elif register_type == register_type_to_int("OW"):
                # output word
                writing_type = module_info.reading_type
                if writing_type.startswith("fs"):
                    val = [self._write_fs(val, **module_info.reading_info)]
                else:
                    val = self._write_ssi(val, **module_info.reading_info)

                self.client_write_registers(
                    offset, "H" * size, val, timeout=self.timeout
                )
            else:
                raise RuntimeError("Not an output module")

    def devwritedigi(self, array_in):
        self.devwritephys(array_in)

    def devreadnocachedigi(self, key):
        # Doing a digital read on an analog channel gives the raw bit value (not converted in voltage, temperature ...)
        # convert_values=False forces this raw reading
        val = self.get(self.devkey2name(key), convert_values=False)

        # needed a conversion to fit the DevShort which is signed
        values = [to_signed(v) for v in flatten([val])]

        return values

    def devreaddigi(self, key):
        val = self.get(self.devkey2name(key), convert_values=False, cached=True)

        # needed a conversion to fit the DevShort which is signed
        values = [to_signed(v) for v in flatten([val])]

        return values

    def devreadnocachephys(self, key):
        return self.get(self.devkey2name(key), flat=True)

    def devreadphys(self, key):
        return self.get(self.devkey2name(key), flat=True, cached=True)

    def devkey2name(self, key):
        """
        From a key (channel enumeration) to the assigned text name

        Example:
            >>> DevKey2Name(3)
            b"gabsTf3"
        """
        return self.modules_config.devkey2name(key)

    def devname2key(self, name):
        """From a logical device (name) to the key"""
        return self.modules_config.logical_keys[name]

    def devwccomm(self, args, sleep_time=0.1):
        """
        Send an command to Wago using the Interlock protocol

        Args:
            args: it is a list or tuple containing ISG commands to be executed.
            sleep_time: introduces some delay between writing requests and reading
                        requests, this is to let the PLC update the memory.
                        If you encounter some unexpected values increasing this
                        time could resolve the problem.

        Note: as the logic was implemented through reverse engineering some parts could
              be not accurate.
        """
        log_debug(self, f"In devwccomm args: {args}")
        command, params = args[0], args[1:]

        """
        PHASE 1: Handshake protocol: starts with PASSWD=0

        Description:
        Write 0x0000 at holding register 0x0100
        """

        addr, data = 0x100, 0x0000  # WC_PASSWD, 0

        log_debug(
            self, f"devwccomm Phase 1: writing at address {addr:04X} value {data:04X}"
        )
        response = self.client.write_registers(addr, "H", [data], timeout=self.timeout)

        """
        PHASE 2: Handshake protocol: wait for OUTCMD==0

        Description: Read n.3 holding registers from address 0x0100

        Example of correct response:

        |  0xaa 0x01 | 0x0000 | 0x0000 |

        The code checks the first byte a fixed value
        the second byte is the version of the ISG software (in this case 1)
        and the last register that should be 0 (ACK)
        """

        addr, size = 0x100, 3

        log_debug(
            self, f"devwccomm Phase 2: reading at address {addr:04X} n.{size} registers"
        )

        start = time.time()
        while True:
            if time.time() - start > self.timeout:
                log_debug(
                    self,
                    f"Last response: Check code (should be like 0xaa 0x01 version tag + version num) is {check:02X}",
                )
                log_debug(self, f"Last response: Ack (should be 0 or 2) is {ack}")
                raise MissingFirmware(f"ACK not received")
            try:
                check, _, ack = self.client_read_input_registers(
                    addr, "H" * size, timeout=self.timeout
                )
            except Exception:
                log_exception(self, f"failed to read at address: {addr} words: {size}")
                raise

            if (check >> 8) != 0xaa:  # check Version Tag
                gevent.sleep(sleep_time)
                continue
            if ack == 0:  # check if is ok
                log_debug(self, "devwccomm Phase 2: ACK received")
                break

        """
        PHASE 3: Handshake protocol: write the command to process and its parameters

        Description: Write command and parameters at address 0x100

        Example of correct request of command 2 with parameters 256:

        Full modbus payload:

         address  word count  byte count passwd tag  command  n. following params   parameter 1
        | 0x0100 |   0x0004   |   0x08   |  0xa5a5  | 0x0002 |       0x0001       |    0x0100   |

        """
        params[:125]  # remove parameters if exceeds the limit

        addr = 0x100  # destination address
        data = []
        data.append(0xa5a5)
        data.append(command)  # command to execute
        data.append(len(params))

        data += list(params)  # adds the parameters

        log_debug(
            self, f"devwccomm Phase 3: writing at address: {addr:04X} values : {data}"
        )

        self.client.write_registers(addr, "H" * len(data), data, timeout=self.timeout)

        """
        PHASE 4: Handshake protocol: wait for end of command (OUTCMD==INCMD or ==0xffff)

        Description: read 4 registers starting from address 0x100

        Example of correct response:

          check    error code   command executed   registers to read
        | 0xaa01 |   0x0000   |      0x0002      |       0x0003      |

        command executed: is the one executed in PHASE 3
        registers to read: is the number to read in PHASE 5
        """

        addr = 0x100
        size = 4
        log_debug(
            self, f"devwccomm Phase 4: reading at address: {addr:04X} words: {size}"
        )

        start = time.time()
        while True:
            if time.time() - start > self.timeout:
                log_debug(
                    self,
                    f"Last response: Command should be {command} and is {command_executed}",
                )
                raise TimeoutError(f"ACK not received")

            try:
                check, error_code, command_executed, registers_to_read = self.client_read_input_registers(
                    addr, "H" * size, timeout=self.timeout
                )
            except Exception:
                log_debug(
                    self,
                    f"devwccomm Phase 4: failed to read at address: {addr} words: {size}",
                )
                raise
            if command != command_executed:
                # PLC is still working on result
                continue
            if error_code != 0:
                log_error(
                    self,
                    f"devwccomm Phase 4 : Command {command_executed} failed with error: 0x{error_code:02X} {ERRORS[error_code]}",
                )
                raise RuntimeError(
                    f"Interlock: Command {command_executed} failed with error: 0x{error_code:02X} {ERRORS[error_code]}"
                )
            else:
                log_debug(
                    self,
                    f"devwccomm Phase 4: ACK from Wago (OUTCMD==INCMD) n.{registers_to_read} registers to read on next request",
                )
                break

        """
        PHASE 5: Read response

        Description: read registers starting from 0x104, the number of regs comes from PHASE 4
        """

        addr = 0x104
        size = registers_to_read
        log_debug(self, f"devwccomm Phase 5: reading at address: {addr} words: {size}")

        if size:
            try:
                response = self.client_read_input_registers(
                    addr, "H" * size, timeout=self.timeout
                )
                if isinstance(response, int):  # single number
                    response = [response]
                log_debug(self, f"read registers response={response}")
            except Exception:
                log_exception(
                    self,
                    f"devwccomm Phase 5: failed to read at address: {addr} words: {size}",
                )
                raise
            return [to_signed(n) for n in response]
        else:
            return []

    def devhard2log(self, array_in):
        """
        Given some information about the position of a register in Wago memory
        it returns the corresponding logical device key and logical channel

        Args:
            channel_type: gives information about input/output type
                          the Most significant byte is either ord('I') for input
                          or ord('O') for Output
                          Least significant byte is either ord('B') for Bit (digital)
                          or ord('W') for Word (analog)

            offset: offset in wago memory, this means that the first digital output
                    will be offset 0, the second digital output will be 1 and so on.
                    If we have an analog output following the digital one the offset
                    starts again from zero.

        Returns: (logical_device_key, logical_device_channel)
        """
        return self.modules_config.devhard2log(array_in)

    def devlog2hard(self, array_in):
        """Gives information about mapping in Wago memory of I?O

        Args:
            Logical Device Key (int)
            Logical Channel (int)
        Notes:
            Logical Channels is 0 if there is only one name associated to that Key

        >>> mapping = "750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl\n750-408,2 foh2pos, sain2, foh2pos, sain4\n750-408, foh2pos, sain6, foh2pos, sain8"
        >>> wago = WagoController("wcdp3")

        >>> wago.devlog2hard((0,2)) # gives the third channel with the name foh2ctrl

        >>> wago.devlog2hard((1,0)) # gives the first channel with the name foh2pos

        >>> wago.devlog2hard((2,0)) # gives the first (and only) channel with the name sain2

        >>> wago.devlog2hard((2,1)) # will fail because there is only one channel with name sain2

        Returns (tuple):
            [0] : offset in wago controller memory (ex: 0x16)
            [1] : MSB=I/O LSB=Bit/Word (ex: 0x4957 = ('I'<<8)+'W')
            [2] : module reference (ex: 469)
            [3] : module number (1st is 0)
            [4] : physical channel of the module (ex: 1 for the 2nd)
        """

        return self.modules_config.devlog2hard(array_in)

    def plugged_modules_description(self):
        out = ""
        for i, m in enumerate(self.attached_modules):
            if m.startswith("750-"):
                description = get_channel_info(m).description
                out += f"module{i}: {m} ({description})\n"
            else:
                out += f"module{i}: I/O mod ({m})\n"
        return out

    def __check_plugged_modules(self):
        """Called at startup to retrieve attached modules configuration from
        the PLC"""
        log_debug(self, "Retrieving attached modules configuration")
        try:
            modules = self.client_read_holding_registers(0x2030, "65H")
        except Exception as exc:
            log_exception(self, f"Can't retrieve Wago plugged modules {exc}")
            raise

        self.__modules = []
        for m in modules:
            if not m:
                break
            else:
                self.__modules.append(WagoController._describe_hardware_module(m))

    def status(self):
        """
        Wago Status information
        """
        out = ""
        if not self.coupler:
            out += f"Controller series code    (INFO_SERIES)    : {self.series}\n"
            out += f"Controller order number    (INFO_ITEM)    : {self.order_nu}\n"
            out += f"Controller firmware revision (INFO_REVISION): {self.firmware['version']}\n"
            out += f"Controller date of firmware  (INFO_DATE)    : {self.firmware['date']}\n"
            out += f"time of firmware  (INFO_TIME)    : {self.firmware['time']}\n"

        out += f"\nWago modules physically plugged and seen by the controller:\n"
        try:
            out += self.plugged_modules_description()
        except Exception:
            log_exception(self, f"Exception on dev_status")
            raise

        out += f"\nWago modules known by the device server:\n"
        for i, mapping in enumerate(self.modules_config.mapping):
            module_reference = mapping["module"]
            module_info = get_channel_info(module_reference)
            out += f"module{i}: {module_reference} ({module_info.description}) {' '.join(flatten(mapping['channels']))}\n"

        out += "\nList of logical devices:\n"
        for logical_device in self.modules_config.read_table.keys():
            for logical_channel in self.modules_config.read_table[
                logical_device
            ].keys():
                logical_device_key = self.modules_config.devname2key(logical_device)
                _, _, _, physical_module, physical_channel = self.modules_config.devlog2hard(
                    (logical_device_key, logical_channel)
                )

            out += f"{logical_device}:\nlogical_channel{logical_channel}: module: {physical_module} channel: {physical_channel}\n"
        try:
            self.check_plugged_modules()
        except RuntimeError as exc:
            out += f"\nConfiguration error: {exc}"
            out += "\nGiven mapping DOES NOT match Wago attached modules"
        else:
            out += "\nGiven mapping does match Wago attached modules"

        return ShellStr(out)

    @staticmethod
    def _describe_hardware_module(register):
        """Given the result of a Wago modbus reading for checking the type
        of the attached modules, returns a Wago module type like '750-469'
        or whenever is not possible a description like '4 Channel Digital Input'
        """
        if register & 0x8000:  # digital in/out
            type_ = "Digital Output" if register & 0x2 else "Digital Input"
            mod_size = (register & 0xf00) >> 8
            return f"{mod_size} Channel {type_}"
            # resulting for example 4ID for a 4 input module
            # and 2OD for a 2 output module
        else:
            return f"750-{register}"

    @property
    def modules(self):
        """Returns real detected modules (including CPU)
        to retrieve given modules configuration use
        .modules_config.modules
        """
        return self.__modules

    @property
    def attached_modules(self):
        """Returns real detected attached modules
        to retrieve given modules configuration use
        .modules_config.attached_modules
        """
        return self.__modules[1:]

    @property
    def logical_keys(self):
        return self.modules_config.logical_keys

    @staticmethod
    def _check_mapping(module1: str, module2: str) -> bool:
        """Compares two given modules and returns True if they are equal
        Args:
            module1
            module2
        Example:
            WagoController._check_mapping("750-400","2 Channel Digital Input")
        """
        # preliminary comparison
        if module1 is None or module2 is None:
            return False
        if module1.startswith("750-") and module2.startswith("750-"):
            return module1 == module2
        elif module1.startswith("750-"):
            # second_mod will be descriptive
            type_mod = module1
            descr_mod = module2
        else:
            type_mod = module2
            descr_mod = module1

        # module2 is a digital

        type_mod_digi_in = get_channel_info(type_mod).digi_in
        type_mod_digi_out = get_channel_info(type_mod).digi_out
        type_mod_type = get_channel_info(type_mod).reading_type

        descr_mod_isinput = True if "Input" in descr_mod else False
        descr_mod_isoutput = True if "Output" in descr_mod else False
        descr_mod_size, _, _, _ = descr_mod.split()
        descr_mod_size = int(descr_mod_size)

        if (
            # check if type is correct
            (
                bool(type_mod_digi_out)
                and descr_mod_isoutput
                or bool(type_mod_digi_in)
                and descr_mod_isinput
            )
            and
            # check if size is correct
            (
                (descr_mod_size == type_mod_digi_in)
                or (descr_mod_size == type_mod_digi_out)
            )
            and type_mod_type == "digital"
        ):
            return True

        return False

    def check_plugged_modules(self):
        """Check configuration between PLC and given config
        and raises an exception if differences are found
        """
        for i, (module1, module2) in enumerate(
            zip_longest(self.attached_modules, self.modules_config.attached_modules)
        ):
            # exclude the CPU main module
            if not WagoController._check_mapping(module1, module2):
                raise RuntimeError(
                    f"PLC module n.{i} (starting from zero) does not corresponds to mapping:{module1} != {module2}"
                )

    def client_read_coils(self, *args, **kwargs):
        with self.lock:
            return self.client.read_coils(*args, **kwargs)

    def client_read_input_registers(self, *args, **kwargs):
        with self.lock:
            return self.client.read_input_registers(*args, **kwargs)

    def client_read_holding_registers(self, *args, **kwargs):
        with self.lock:
            return self.client.read_holding_registers(*args, **kwargs)

    def client_write_registers(self, address, struct_format, values, timeout=None):
        if self.order_nu == 891:
            """For Wago CPU model 750-891

            Protocol description:
            -----------------------------------------------------------------
            fcode (1 word) : Function Code (15 for write multiple coil,
                             16 for multiple registers)
            faddr (1 word) : Wago starting address (internal memory)
            fnum_words (1 word) : Num of words to be written 
                                  (For FC15 always 1)
            fmask (1 word) : Bitmask used in FC15 for writing only some coils
            ftable (n words) : Array of values (always 1 word for FC15)
            """
            payload = [16, address, len(struct_format), 0, *values]

            # allow writing if previous request was ok
            with gevent.Timeout(
                timeout, RuntimeError("PLC is not ready to receive requests")
            ):
                while True:
                    if self.client_read_holding_registers(12288, "H") == 0:
                        # when the Function Code is set to 0 we can proceed
                        break
            with self.lock:
                value = self.client.write_registers(
                    12288, "H" * len(payload), payload, timeout=self.timeout
                )
            return value
        else:
            with self.lock:
                value = self.client.write_registers(
                    address, struct_format, values, timeout=timeout
                )
            return value

    def client_write_coil(self, address, on_off, timeout=None):
        if self.order_nu == 891:
            word_address = address // 16 + self.modules_config.bit_output_mem_area
            bit_n = address % 16
            bit_mask = 1 << bit_n
            lenght = 1
            value = bit_mask if on_off else 0

            payload = [15, word_address, lenght, bit_mask, value]
            log_debug_data(self, "payload of client_write_coil", payload)

            with gevent.Timeout(
                timeout, RuntimeError("PLC is not ready to receive requests")
            ):
                while True:
                    if self.client_read_holding_registers(12288, "H") == 0:
                        # when the Function Code is set to 0 we can proceed
                        break

            with self.lock:
                self.client.write_registers(
                    12288, "H" * len(payload), payload, timeout=self.timeout
                )
        else:
            with self.lock:
                self.client.write_coil(address, on_off, timeout=timeout)


class WagoCounter(SamplingCounter):
    """ Counter reading and gains reading/setting
    """

    def __init__(self, name, parent, index=None, **kwargs):
        SamplingCounter.__init__(self, name, parent, **kwargs)
        self.index = index
        self.parent = parent
        self.cntname = name

    def __call__(self, *args, **kwargs):
        return self

    def gain(self, gain=None, name=None):
        """ Set/read the gain. The gain is set by applying values on 3 channels.
        Args:
            gain (int): value of the gain. Accepted values: 0-7.
                        Read the gain if no value
            name (str): counter name - optional.
        Raises:
            ValueError: the gain is out of the limits (0-7)
        """
        name = name or self.cntname
        try:
            name = [x for x in self.parent.counter_gain_names if str(name) in x][0]
        except IndexError:
            return None

        n_channels = 3

        if gain is None:
            # Reading
            valarr = self.parent.get(name)
            if isinstance(valarr, list) and True in valarr:
                if valarr.count(True) == 1:
                    return valarr.index(True) + 1
                if valarr.count(True) == n_channels:
                    return 7
                val = 0
                for idx in range(n_channels):
                    if valarr[idx]:
                        val += idx
                return val + n_channels
            return 0

        n_val = 2 * n_channels + 1
        if gain < 0 or gain > n_val:
            raise ValueError("Gain out of limits")

        if gain == n_val:
            valarr = [True] * n_channels
        else:
            valarr = [False] * n_channels
            if gain > n_channels:
                gain1 = gain // n_channels - 1
                gain2 = gain - n_channels - gain1
                valarr[gain1] = True
                valarr[gain2] = True
            elif gain > 0:
                valarr[gain - 1] = True

        self.parent.set(name, valarr)
        return gain


class Wago(SamplingCounterController):
    """ The wago class
    """

    def __init__(self, name, config_tree):
        """
        mapping:
            -
                type: 750-412
                logical_names: ab, cd, de
            -
                type: 750-412
                logical_names: ab, cd, de

        interlocks:
        """

        super().__init__(name=name)

        # parsing config_tree
        self.__filename = config_tree.filename

        self.modules_config = ModulesConfig.from_config_tree(config_tree)

        self.cnt_dict = {}
        self.cnt_names = []
        self.cnt_gain_names = []

        try:
            self.counter_gain_names = (
                config_tree["counter_gain_names"].replace(" ", "").split(",")
            )
        except Exception:
            pass

        try:
            self.cnt_names = config_tree["counter_names"].replace(" ", "").split(",")
        except Exception:
            pass
        else:
            for i, nam in enumerate(self.cnt_names):
                self.cnt_dict[nam] = i
                add_property(self, nam, WagoCounter(nam, self, i))

        # instantiating comm and controller class
        if config_tree.get("tango"):
            try:
                # if tango url is provided do not consider modbustcp
                new_config_tree = config_tree.copy()
                del new_config_tree["modbustcp"]
            except KeyError:
                pass
            try:
                comm = get_comm(new_config_tree)
            except Exception:
                log_exception(self, "Can't connect to tango host")
                raise
            if not len(self.modules_config.attached_modules):
                # if no config is provided for DeviceProxy get tango property
                mapping = comm.get_property("config")["config"]
                self.modules_config = ModulesConfig.from_tango_config(mapping)
            self.controller = TangoWago(comm, self.modules_config)
        else:
            comm = get_wago_comm(config_tree)
            self.controller = WagoController(comm, self.modules_config)
            self.controller.connect()

        global_map.register(
            self,
            parents_list=["wago"],
            children_list=[self.controller],
            tag=f"Wago({self.name})",
        )

        self.__interlock_load_config(config_tree)

    def __interlock_load_config(self, config_tree):
        try:
            config_tree["interlocks"]
        except KeyError:
            # no interlock is defined on beacon or configuration mistake
            pass
        else:
            try:
                from bliss.controllers.wago.interlocks import beacon_interlock_parsing

                self._interlocks_on_beacon = beacon_interlock_parsing(
                    config_tree["interlocks"], self.modules_config
                )
            except Exception as exc:
                msg = f"Interlock parsing error on Beacon config: {exc!r}"
                log_error(self, msg)

    def __info__(self):
        keys = list(self.modules_config.logical_keys.keys())

        tab = [
            ["logical device", "logical channel", "module_type", "module description"]
        ]
        for k in keys:
            for ch in self.modules_config.read_table[k].keys():
                ty = self.modules_config.read_table[k][ch]["module_reference"]
                desc = get_channel_info(ty).description
                tab.append([k, ch, ty, desc])
        repr_ = tabulate(tab, headers="firstrow", stralign="center")
        try:
            self.controller.status()
        except Exception as exc:
            repr_ += f"\n\n** Could not retrieve hardware mapping ({exc})**"
            log_error(self.controller, "Could not retrieve status")
        else:
            if "DOES NOT match" in self.controller.status():
                repr_ += "\n\n** Given mapping DOES NOT match Wago attached modules **"
                repr_ += (
                    f"\n\nHINT: check {self.name}.status() to have debug information"
                )
            else:
                repr_ += "\n\nGiven mapping does match Wago attached modules"

        return repr_

    def close(self):
        log_debug(self, f"In close")
        self.controller.close()

    def __close__(self):
        self.close()

    def status(self):
        return self.controller.status()

    def interlock_reset(self, instance_num, ask=True):
        from bliss.controllers.wago.interlocks import interlock_reset as reset

        reset(self.controller, instance_num)

    def interlock_show(self):
        from bliss.shell.interlocks import interlock_show as show

        show(self)

    def interlock_upload(self, ask=True):
        log_debug(self, f"Reloading Wago interlocks static config")
        from bliss.config.static import get_config_dict

        reloaded_config = get_config_dict(self.__filename, self.name)

        self.__interlock_load_config(reloaded_config)

        from bliss.controllers.wago.interlocks import interlock_download as download
        from bliss.controllers.wago.interlocks import interlock_compare as compare
        from bliss.controllers.wago.interlocks import interlock_upload as upload

        repr_ = []
        try:
            self._interlocks_on_beacon
        except AttributeError:
            raise AttributeError("Interlock configuration is not present in Beacon")
        try:
            interlocks_on_plc = download(self.controller, self.modules_config)
        except MissingFirmware:
            raise MissingFirmware("No ISG Firmware loaded into wago")
        else:
            are_equal, messages = compare(self._interlocks_on_beacon, interlocks_on_plc)
        if are_equal:
            repr_.append("No need to upload the configuration")
        else:
            if ask:
                yes_no = input(
                    "Are you sure that you want to upload a new configuration? (Answer YES to proceed)"
                )
            else:
                yes_no = "YES"

            if yes_no == "YES":
                upload(self.controller, self._interlocks_on_beacon)
                # double check
                interlocks_on_plc = download(self.controller, self.modules_config)
                are_equal, messages = compare(
                    self._interlocks_on_beacon, interlocks_on_plc
                )
                if are_equal:
                    repr_.append("Configuration succesfully upload")
                else:
                    repr_.append(
                        "Something gone wrong: configurations are not the same"
                    )

        return ShellStr("\n".join(repr_))

    def interlock_to_yml(self):
        from bliss.controllers.wago.interlocks import interlock_to_yml as to_yml
        from bliss.controllers.wago.interlocks import interlock_download as download

        try:
            return ShellStr(to_yml(download(self.controller, self.modules_config)))
        except MissingFirmware:
            raise MissingFirmware("No ISG Firmware loaded into wago")

    def interlock_state(self):
        from bliss.controllers.wago.interlocks import interlock_state as state

        return state(self.controller)

    def _safety_check(self, *args):
        return True

    @synchronized()
    def set(self, *args, **kwargs):
        """Set one or more logical_devices
        Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        if not self._safety_check(*args):
            return
        return self.controller.set(*args, **kwargs)

    @synchronized()
    def get(self, *args, **kwargs):
        """Read one or more values from channels
        Args:
            *channel_names (list): list of channels to be read
            convert_values (bool): default=True converts from raw reading to meaningful values

        Returns:
            (list): channel values
        """
        return self.controller.get(*args, **kwargs)

    @property
    def logical_keys(self):
        return list(self.modules_config.logical_keys.keys())

    @property
    def counters(self):
        """Get the list of the configured counters
        Returns:
            (list): list of the configured counter objects
        """
        counters_list = []
        for cnt_name in self.cnt_names:
            counters_list.append(getattr(self, cnt_name))
        return counter_namespace(counters_list)

    def _cntread(self, acq_time=None):
        if len(self.cnt_names) == 1:
            return [self.get(*self.cnt_names)]
        return self.get(*self.cnt_names)

    def read_all(self, *counters):
        """Read all the counters
        Args:
            *counters (list): names of counters to be read
        Returns:
            (list): read values from counters
        """
        cnt_names = [cnt.name.replace(self.name + ".", "") for cnt in counters]
        result = self.get(*cnt_names)
        return result if isinstance(result, list) else [result]


class WagoMockup(Wago):
    def __init__(self, name, config_tree):
        self.modules_config = ModulesConfig.from_config_tree(config_tree)

        from bliss.controllers.wago.emulator import WagoEmulator

        self.__mockup = WagoEmulator(self.modules_config)

        # configure comm.
        config_tree["modbustcp"] = {"url": f"localhost:{self.__mockup.port}"}

        super().__init__(name, config_tree)

    def close(self):
        super().close()
        try:
            self.__mockup.close()
        except AttributeError:
            pass
