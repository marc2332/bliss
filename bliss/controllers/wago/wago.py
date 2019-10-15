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
import re
import logging
import collections
from enum import Enum

from prompt_toolkit import print_formatted_text, HTML

import tango

import bliss.common.measurement
from bliss.common.utils import add_property, flatten
from bliss.config.conductor.client import synchronized
from bliss import global_map
from bliss.common.logtools import *
from bliss.common.measurement import SamplingCounter, counter_namespace
from bliss.controllers.wago.helpers import splitlines, to_signed


"""
EXPLANATION AND NAMING CONVENTION

PHYSICAL MAPPING

Every Wago PLC is normally assembled with a central unit (Wago PLC Ethernet/IP type 750-842) plus a variable numbers of addons as needed.
Addon modules usually has one or more input/output that can be plugged to the outside world.

Naming Convention:

 * PHYSICAL_MODULES: (int) hardware modules with I/O that you physically compose to obtain the physical configuration, we will number them from 0 (first hardware module) to n.
 * PHYSICAL_CHANNELS: (int) I/O inside one PHYSICAL_MODULE, we will number them from 0 (first channel) to n.

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
                on physical module n.1 (channels n.0 and n.2) and two are
                situated on physical module n.2 (channels n.0 and n.2)
        sain2 has 2 logical channels situated on physical module n.1 on channels n.1 and n.3
        sain6 has 1 logical channel situated on physical module n.2 on channel n.1
        sain8 has 1 logical channel situated on physical module n.2 on channel n.3


"""


WAGO_CONTROLLERS = {}


DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT, N_CHANNELS, READING_TYPE, DESCRIPTION, READING_INFO, WRITING_INFO = (
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
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
    "digi_in digi_out ana_in ana_out n_channels reading_type description reading_info writing_info".split(),
)

MODULES_CONFIG = {
    # [Digital IN, Digital OUT, Analog IN, Analog OUT, Total, type]
    # types are:
    # fs4-20: 4/20mA
    # fs20: 4/20mA
    # fs10: 0/10V
    # thc: thermocouple
    # ssi24: 24 bit SSI encoder
    # ssi32: 32 bit SSI encoder
    # digital: digital IN or OUT
    # counter: counters
    "750-842": [0, 0, 0, 0, 2, "none", "Wago PLC Ethernet/IP"],
    "750-400": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-401": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-402": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-403": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-404": [0, 0, 3, 0, 3, "counter", "32 bit Counter"],
    "750-405": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-406": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-408": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-409": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-410": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-411": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-412": [2, 0, 0, 0, 2, "digital", "2 Channel Digital Input"],
    "750-414": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-415": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-422": [4, 0, 0, 0, 4, "digital", "4 Channel Digital Input"],
    "750-430": [8, 0, 0, 0, 8, "digital", "8 Channel Digital Input"],
    "750-436": [8, 0, 0, 0, 8, "digital", "8 Channel Digital Input"],
    "750-452": [0, 0, 2, 0, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-454": [0, 0, 2, 0, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-455": [0, 0, 4, 0, 4, "fs4-20", "4 Channel 4/20mA Input"],
    "750-456": [0, 0, 2, 0, 2, "fs10", "2 Channel +-10V Differential Input"],
    "750-457": [0, 0, 4, 0, 4, "fs10", "4 Channel +-10V Input"],
    "750-459": [0, 0, 4, 0, 4, "fs10", "4 Channel Channel 0/10V Input"],
    "750-461": [0, 0, 2, 0, 2, "thc", "2 Channel PT100 Input"],
    "750-462": [0, 0, 2, 0, 2, "thc", "2 Channel Thermocouple Input"],
    "750-465": [0, 0, 2, 0, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-466": [0, 0, 2, 0, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-467": [0, 0, 2, 0, 2, "fs10", "2 Channel 0/10V Input"],
    "750-468": [0, 0, 4, 0, 4, "fs10", "4 Channel 0/10V Input"],
    "750-469": [0, 0, 2, 0, 2, "thc", "2 Channel Ktype Thermocouple Input"],
    "750-472": [0, 0, 2, 0, 2, "fs20", "2 Channel 0/20mA 16bit Input"],
    "750-474": [0, 0, 2, 0, 2, "fs4-20", "2 Channel 4/20mA 16bit Input"],
    "750-476": [0, 0, 2, 0, 2, "fs10", "2 Channel +-10V Input"],
    "750-477": [0, 0, 2, 0, 2, "fs20", "2 Channel 0/10V Differential Input"],
    "750-478": [0, 0, 2, 0, 2, "fs10", "2 Channel 0/10V Input"],
    "750-479": [0, 0, 2, 0, 2, "fs10", "2 Channel +-10V Input"],
    "750-480": [0, 0, 2, 0, 2, "fs20", "2 Channel 0/20mA Input"],
    "750-483": [0, 0, 2, 0, 2, "fs30", "2 Channel 0/30V Differential Input"],
    "750-485": [0, 0, 2, 0, 2, "fs4-20", "2 Channel 4/20mA Input"],
    "750-492": [0, 0, 2, 0, 2, "fs4-20", "2 Channel 4/20mA Differential Input"],
    "750-501": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-502": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-504": [0, 4, 0, 0, 4, "digital", "4 Channel Digital Output"],
    "750-506": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-507": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-508": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-509": [0, 2, 0, 0, 2, "digital", "2 Channel Digital Output"],
    "750-512": [0, 2, 0, 0, 2, "digital", "2 Normally Open Relay Output"],
    "750-513": [0, 2, 0, 0, 2, "digital", "2 Normally Open Relay Output"],
    "750-514": [0, 2, 0, 0, 2, "digital", "2 Changeover Relay Output"],
    "750-516": [0, 4, 0, 0, 4, "digital", "4 Channel Digital Output"],
    "750-517": [0, 2, 0, 0, 2, "digital", "2 Changeover Relay Output"],
    "750-519": [0, 4, 0, 0, 4, "digital", "4 Channel Digital Output"],
    "750-530": [0, 8, 0, 0, 8, "digital", "8 Channel Digital Output"],
    "750-531": [0, 4, 0, 0, 4, "digital", "4 Channel Digital Output"],
    "750-536": [0, 8, 0, 0, 8, "digital", "8 Channel Digital Output"],
    "750-550": [0, 0, 0, 2, 2, "fs10", "2 Channel 0/10V Output"],
    "750-552": [0, 0, 0, 2, 2, "fs20", "2 Channel 0/20mA Output"],
    "750-554": [0, 0, 0, 2, 2, "fs4-20", "2 Channel 4/20mA Output"],
    "750-556": [0, 0, 0, 2, 2, "fs10", "2 Channel +-10V Output"],
    "750-557": [0, 0, 0, 4, 4, "fs10", "4 Channel +-10V Output"],
    "750-562": [0, 0, 0, 2, 2, "fs10", "2 Channel +-10V 16bit Output"],
    "750-562-UP": [0, 0, 0, 2, 2, "fs10", "2 Channel 0/10V 16bit Output"],
    "750-630": [0, 0, 2, 0, 1, "ssi24", "24 bit SSI encoder"],  # special
    "750-630-24": [0, 0, 2, 0, 1, "ssi24", "24 bit SSI encoder"],  # special
    "750-630-32": [0, 0, 2, 0, 1, "ssi32", "32 bit SSI encoder"],  # special
    "750-637": [0, 0, 4, 4, 2, "637", "32 bit Incremental encoder"],  # special
    "750-653": [0, 0, 2, 2, 1, "653", "RS485 Serial Interface"],  # special
    # check wcid31user for the followings
    "750-1416": [8, 0, 0, 0, 8, "digital", "8 Channel Digital Input"],
    "750-1417": [8, 0, 0, 0, 8, "digital", "8 Channel Digital Input"],
    "750-1515": [0, 8, 0, 0, 8, "digital", "8 Channel Digital Output"],
}


def get_module_info(module_name):
    return MODULES_CONFIG[module_name]


# go through catalogue entries and update 'reading info'
for module_name, module_info in MODULES_CONFIG.items():
    reading_info = {}
    writing_info = {}

    # replacing Configuration List with a NamedTuple
    MODULES_CONFIG[module_name] = ModConf(*module_info, reading_info, writing_info)

    reading_type = module_info[READING_TYPE]
    if reading_type.startswith("fs"):
        module_info[READING_TYPE] = "fs"
        try:
            fs_low, fs_high = map(int, reading_type[2:].split("-"))
        except ValueError:
            fs_low = 0
            fs_high = int(reading_type[2:])
        else:
            if fs_low != 0:
                fs_high -= fs_low

        reading_info["low"] = fs_low
        reading_info["high"] = fs_high
        if module_name.endswith("477"):
            reading_info["base"] = 20000
        elif module_name.endswith("562-UP"):
            reading_info["base"] = 65535
        else:
            reading_info["base"] = 32768
    elif reading_type.startswith("ssi"):
        module_info[READING_TYPE] = "ssi"
        reading_info["bits"] = int(reading_type[3:])
    elif reading_type.startswith("thc"):
        module_info[READING_TYPE] = "thc"
        reading_info["bits"] = 16


def BlissWago(comm, modules_config):
    """Return WagoController instance, unique for a particular host"""

    with gevent.Timeout(3):
        host = comm.host
        port = comm.port
        fqdn = socket.getfqdn(host)

    try:
        wc = WAGO_CONTROLLERS[f"{fqdn}:{port}"]
    except KeyError:
        wc = WagoController(comm, modules_config)
        WAGO_CONTROLLERS[f"{fqdn}:{port}"] = wc

    return wc


class TangoWago:
    def __init__(self, tango_url, modules_config):
        """
        Bridge beetween Wago `user` class and
        a tango Device Server
        """
        self.tango_url = tango_url
        self.modules_config = modules_config
        self._proxy = tango.DeviceProxy(tango_url)

    def get(self, *args, **kwargs):
        values = []
        for name in args:
            key = self.modules_config.devname2key(name)
            val = self._proxy.command_inout("DevReadNoCachePhys", key)
            values.append(val)
        return flatten(values)

    def set(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        # write_table = self.modules_config._resolve_write(*args)
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

        for logical_device, *values in channels_to_write:
            logical_device_key = self.modules_config.devname2key(logical_device)

            array = [logical_device_key]
            for channel, val in enumerate(flatten(values)):
                array.extend([channel, val])
            # logical_device_key, than pairs of channel,values
            self._proxy.command_inout("devwritephys", array)

    def __getattr__(self, attr):
        return getattr(self._proxy, attr)


class ModulesConfig:
    def __init__(self, mapping_str, main_module="750-842", ignore_missing=False):
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
        self.mapping_str = mapping_str
        i = 0
        digi_out_base = 0
        ana_out_base = 0
        self.__mapping = []
        self.__modules = [main_module]  # first element is the Ethernet Module
        for module_name, channels in ModulesConfig.parse_mapping_str(mapping_str):
            if module_name not in MODULES_CONFIG:
                raise RuntimeError("Unknown module: %r" % module_name)
            self.__modules.append(module_name)
            channels_map = []
            module_info = get_module_info(module_name)
            if channels:
                # if channels are specified, check it corresponds
                # to the number of available channels
                if module_info[N_CHANNELS] != len(channels):
                    if not ignore_missing:
                        raise RuntimeError(
                            "Missing mapped channels on module %d: %r"
                            % (i + 1, module_name)
                        )
                for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                    channels_map.append([])
                    for _ in range(module_info[j]):
                        if module_info[N_CHANNELS] == 1:
                            channels_map[-1].append(channels[0])
                        else:
                            try:
                                channels_map[-1].append(channels.pop(0))
                            except IndexError:
                                if ignore_missing:
                                    pass
                                else:
                                    raise
            self.__mapping.append(
                {
                    "module": module_name,
                    "channels": channels_map,
                    "writing_info": {DIGI_OUT: digi_out_base, ANA_OUT: ana_out_base},
                    "n_channels": module_info[N_CHANNELS],
                }
            )
            digi_out_base += module_info[DIGI_OUT]
            ana_out_base += module_info[ANA_OUT]
            i += 1

    @property
    def mapping(self):
        return self.__mapping

    @property
    def modules(self):
        """Returns all vendor modules of PLC

        Example:
            >>> wago.modules
            ['750-842', '750-430', '740-456']
        """
        return self.__modules

    @property
    def attached_modules(self):
        """Returns all attached modules of PLC (excluding CPU module)
        Example:
            >>> wago.modules
            ['750-430', '740-456']
        """
        return self.__modules[1:]

    @staticmethod
    def parse_mapping_str(mapping_str: str):
        """
        Parse a configuration string and yields plc module informations

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

        return cls("\n".join(mapping), ignore_missing=ignore_missing)

    @classmethod
    def from_tango_config(cls, config: dict):
        """Alternative constructor with Wago Device Server 
        config property"""

        return cls("\n".join(config), ignore_missing=True)

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
        if isinstance(channel_type, str):
            # converto to integer if receiving types like 'TC' or 'IB'
            channel_type = (ord(channel_type[0]) << 8) + ord(channel_type[1])
        for logical_device_key, logical_channels in enumerate(
            self.logical_mapping.values()
        ):
            for logical_channel, logical_channel_info in enumerate(logical_channels):
                physical_channel, physical_module, module_type, channel_base_address, offset_ = (
                    logical_channel_info
                )
                if offset_ == offset and channel_base_address == channel_type:
                    return logical_device_key, logical_channel

    def devlog2hard(self, array_in):

        device_key, logical_channel = array_in
        logical_device = self.devkey2name(device_key)

        i = 0
        device = self.logical_mapping[logical_device][logical_channel]
        physical_channel = device.physical_channel
        physical_module = device.physical_module
        channel_base_address = device.channel_base_address
        offset = device.offset
        module_reference = int(device.module_type.split("-")[1])

        return (
            offset,
            channel_base_address,
            module_reference,
            physical_module,
            physical_channel,
        )

    def devlog2scale(self, array_in):
        raise NotImplementedError
        logical_name, logical_channel = array_in
        _, _, module_type, _, _ = self.logical_mapping[logical_name][logical_channel]
        return scale

    def keys(self):
        return self.logical_keys.values()

    def _resolve_read(self, *channel_names):
        """
        Resolve modules/channels to be read on PLC
        Args:
            *channel_names (list): list of channels to be read
        Returns:
            (list): one list of three elements for every PLC's module that has to be read
                    containing: module number (from 0 to n)
                                type of I/O: (0=DIGI_IN, 1=DIGI_OUT, 2=ANA_IN, 3=ANA_OUT)
                                module internal IN/OUT number (from 0 to n)
        Return example:
            [[(0, 2, 0), (0, 2, 1)], [(2, 2, 1)], [(6, 2, 1)]]
            Means that we want to read:
            - Digital IN of channel 0 and 1 of module 0
            - Digital IN of channel 1 of module 2
            - Digital IN of channel 1 of module 6
        """
        channels_to_read = []
        found_channel = set()
        for channel_name in channel_names:
            # find module(s) corresponding to given channel name
            # all multiple channels with the same name will be retrieved
            for i, mapping_info in enumerate(self.mapping):
                channels_map = mapping_info["channels"]
                if channels_map:
                    for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                        if channel_name in channels_map[j]:
                            found_channel.add(channel_name)
                            channels_to_read.append([])
                            if mapping_info["n_channels"] == 1:
                                channels_map[j] = [channels_map[j][0]]
                            for k, chan in enumerate(channels_map[j]):
                                if chan == channel_name:
                                    channels_to_read[-1].append((i, j, k))

        not_found_channels = set(channel_names) - found_channel
        if not_found_channels:
            raise KeyError(
                f"Channel(s) '{not_found_channels}` doesn't exist in Mapping"
            )

        # return tuple info: MODULE_NUM, IOTYPE, MOD_INT_CHANNEL
        return channels_to_read

    def _resolve_write(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        Args:
            list or pairs:  channel_name, value
                            or a list with channel_name, val1, val2, ..., valn
                            or a combination of the two

        Returns:
            write_table:

        """
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

        write_table = {}
        n_chan = 0
        found_channel = set()
        channel_names = set()
        for channel_name, value in channels_to_write:
            channel_names.add(channel_name)
            for i, mapping_info in enumerate(self.mapping):
                channel_map = mapping_info["channels"]
                if not channel_map:
                    continue
                for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                    n_channels = channel_map[j].count(channel_name)
                    if n_channels:
                        found_channel.add(channel_name)
                        if j not in (DIGI_OUT, ANA_OUT):
                            raise RuntimeError(
                                "Cannot write: %r is not an output" % channel_name
                            )
                        if isinstance(value, list):
                            if n_channels > len(value):
                                raise RuntimeError(
                                    "Cannot write: not enough values for channel %r: expected %d, got %d"
                                    % (channel_name, n_channels, len(value))
                                )
                            else:
                                idx = -1
                                for k in range(n_channels):
                                    idx = channel_map[j].index(channel_name, idx + 1)

                                    write_table.setdefault(i, []).append(
                                        (j, idx, value[n_chan + k])
                                    )
                        else:
                            if n_channels > 1:
                                raise RuntimeError(
                                    "Cannot write: only one value given for channel %r, expected: %d"
                                    % (channel_name, n_channels)
                                )
                            k = channel_map[j].index(channel_name)
                            write_table.setdefault(i, []).append((j, k, value))
                        n_chan += n_channels
        not_found_channels = channel_names - found_channel
        if not_found_channels:
            raise KeyError(
                f"Channel(s) '{not_found_channels}` doesn't exist in Mapping"
            )

        return write_table

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
    def logical_mapping(self):
        """
        Maps logical devices/channels to physical modules/channels

        Returns: dictionary where keys are logical devices, values are list of namedtuple

        Example:
            >>> self.logical_mapping['dac6'][0] # asking the fist logical channel of 'dac6' logical device
            PhysMap(physical_channel=1, physical_module=7, module_type='750-562', channel_base_address=20311, offset=5)
            >>> # second physical channel (n.1) of eighth physical module (n.7) of type 750-562, ...
        """
        try:
            self.__logical_mapping
        except AttributeError:
            PhysMap = collections.namedtuple(
                "PhysMap",
                (
                    "physical_channel",
                    "physical_module",
                    "module_type",
                    "channel_base_address",
                    "offset",
                ),
            )

            # create a dictionary with logical_device as key and an empty list as values
            # {'th21':[],'gil1':[], ..}
            self.__logical_mapping = {k: list() for k in self.logical_keys.keys()}
            for physical_device, mapping in self.physical_mapping.items():
                logical_device, physical_channel, physical_module, module_type, channel_base_address, offset = (
                    mapping
                )
                self.__logical_mapping[logical_device].append(
                    PhysMap(
                        physical_channel,
                        physical_module,
                        module_type,
                        channel_base_address,
                        offset,
                    )
                )

        return self.__logical_mapping

    @property
    def physical_mapping(self):
        """
        Returns:
            dict of LogPhysMap: a dict with LOGICAL DEVICE KEYS as keys (starting fron 0 to n)

                LogPhysMap fields:
                 - logical_device
                 - physical_channel
                 - physical_module
                 - physical_module_type
                 - channel_base_address
                 - offset

        Example:
            >>> self.physical_mapping[3]
            LogPhysMap(logical_device='pot2cur', physical_channel=1, physical_module=1,
                    module_type='750-476', channel_base_address=18775, offset=3)

            meaning the second channel (1) of the second PLC module (1) with logical name pot2cur
            PLC add-on module of type 750-476, channel base address 18775 and offset 3

        """
        try:
            self.__physical_mapping
        except AttributeError:
            LogPhysMap = collections.namedtuple(
                "LogPhysMap",
                (
                    "logical_device",
                    "physical_channel",
                    "physical_module",
                    "module_type",
                    "channel_base_address",
                    "offset",
                ),
            )

            all_channels = []
            digi_in, digi_out, ana_in, ana_out = 0, 0, 0, 0

            for physical_module, mapping_info in enumerate(self.mapping):
                channels_map = mapping_info["channels"]
                module_type = mapping_info["module"]

                # some channels may not have a name but we have
                # to take them into account to calculate the proper
                # logical_channel
                total_n_channels = mapping_info["n_channels"]
                required_channel_list = flatten(channels_map)
                all_channels_map = required_channel_list + [None] * (
                    total_n_channels - len(required_channel_list)
                )

                for logical_channel, logical_device in enumerate(all_channels_map):
                    # getting channel base address
                    module_info = MODULES_CONFIG[module_type]
                    if module_info[DIGI_IN] > 0 and module_info[DIGI_OUT] > 0:
                        if logical_channel % 2:
                            channel_base_address = (ord("I") << 8) + ord(
                                "B"
                            )  # Corresponds 0x4942 18754
                        else:
                            channel_base_address = (ord("O") << 8) + ord(
                                "B"
                            )  # Corresponds 0x4f42 20290
                    elif module_info[DIGI_IN] > 0:
                        channel_base_address = (ord("I") << 8) + ord(
                            "B"
                        )  # Corresponds 0x4942 18754
                        offset = digi_in
                        digi_in += 1
                    elif module_info[DIGI_OUT] > 0:
                        channel_base_address = (ord("O") << 8) + ord(
                            "B"
                        )  # Corresponds 0x4f42 20290
                        offset = digi_out
                        digi_out += 1
                    elif module_info[ANA_IN] > 0:
                        channel_base_address = (ord("I") << 8) + ord(
                            "W"
                        )  # Corresponds 0x4957 18775
                        offset = ana_in
                        ana_in += 1
                    elif module_info[ANA_OUT] > 0:
                        channel_base_address = (ord("O") << 8) + ord(
                            "W"
                        )  # Corresponds 0x4f57 20311
                        offset = ana_out
                        ana_out += 1

                    if (
                        logical_device
                    ):  # exclude None channels (that does not have a name)
                        all_channels.append(
                            LogPhysMap(
                                logical_device,
                                logical_channel,
                                physical_module,
                                module_type,
                                channel_base_address,
                                offset,
                            )
                        )
            self.__physical_mapping = {
                key: info for key, info in enumerate(all_channels)
            }
        return self.__physical_mapping


class MissingFirmware(RuntimeError):
    pass


class WagoController:
    """
    The wago controller class
    """

    def __init__(self, comm, modules_config: ModulesConfig, timeout=1.0):

        self.client = comm
        self.timeout = timeout
        self.modules_config = modules_config

        self.series, self.order_nu = 0, 0
        self.firmware = {"date": "", "version": 0, "time": ""}

        self.coupler = False

        self.lock = gevent.lock.Semaphore()
        global_map.register(self, tag=f"Engine")

    def connect(self):
        """ Connect to the wago. Check if we have a coupler or a controller.
        In case of controller get the firmware version and firmware date.
        """
        with self.lock:
            log_debug(self, "In connect of wago")
            # check if we have a coupler or a controller
            self.series = self.client.read_input_registers(0x2011, "H")

            self.order_nu = self.client.read_input_registers(0x2012, "H")

            self.coupler = self.order_nu < 800
            if not self.coupler:
                # get firmware date and version
                reply = self.client.read_input_registers(0x2010, "H")
                self.firmware["version"] = reply
                reply = struct.pack(
                    "8H", *self.client.read_input_registers(0x2022, "8H")
                )
                self.firmware["date"] = "/".join(
                    (x.decode("utf-8") for x in reply.split(b"\x00") if x)
                )
                reply = struct.pack(
                    "8H", *self.client.read_input_registers(0x2021, "8H")
                )
                self.firmware["time"] = "/".join(
                    (x.decode("utf-8") for x in reply.split(b"\x00") if x)
                )

    def close(self):
        """
        Close the connection.
        """
        with self.lock:
            self.client.close()

    def _read_fs(self, raw_value, low=0, high=10, base=32768):
        """Read Digital Input type module. Make full scale conversion.
        """
        value = ctypes.c_short(raw_value).value
        return (value * high / float(base)) + low

    def _read_ssi(self, raw_value, bits=24):
        """Read SSI (absolute encoders) type module
        Returns:
            (float): 24 bits precision, signed float
        """
        # reading is two words, 16 bits each
        value = raw_value[0] + raw_value[1] * (1 << 16)
        value &= (1 << bits) - 1
        if value & (1 << (bits - 1)):
            value -= 1 << bits
        return [float(value)]

    def _read_thc(self, raw_value, bits=16):
        """Read a thermocouple type module.
        Returns:
            (float): signed float
        """
        value = ctypes.c_ushort(raw_value).value
        value &= (1 << bits) - 1
        if value & (1 << (bits - 1)):
            value -= 1 << bits
        return value / 10.0

    def _read_value(self, raw_value, read_table):
        """ Read raw value from a module
        """
        reading_type = read_table[READING_TYPE]
        reading_info = read_table[READING_INFO]
        if reading_type == "fs":
            return self._read_fs(raw_value, **reading_info)
        if reading_type == "ssi":
            return self._read_ssi(raw_value, **reading_info)
        if reading_type == "thc":
            return self._read_thc(raw_value, **reading_info)
        return raw_value

    def read_phys(self, modules_to_read, convert_values=True):
        """
        Read physical values

        Args:
            modules_to_read(list): list of modules to read (from 0 to n)

        Returns:
            (tuple of tuples): a tuple containing all obtained values

        Examples:
            >>># reading 3 modules, first is 4 Digital OUT, second  4 Digital IN
            >>># third is 2 Analog IN
            >>>read_phys((0,1,2))

            (
              (None, (0, 1, 0, 0), None, None),
              ((0, 1, 1, 0), None, None, None),
              (None, None, (-0.123, 0.0), None),
            )

        """
        # modules_to_read has to be a sorted list
        ret = []
        read_table = []
        total_digi_in, total_digi_out, total_ana_in, total_ana_out = 0, 0, 0, 0

        for module_index, module in enumerate(self.modules_config.mapping):
            module_name = module["module"]
            try:
                module_info = get_module_info(module_name)
            except KeyError:
                raise RuntimeError(
                    "Cannot read module %d: unknown module %r"
                    % (module_index, module_name)
                )
            n_digi_in = module_info[DIGI_IN]
            n_digi_out = module_info[DIGI_OUT]
            n_ana_in = module_info[ANA_IN]
            n_ana_out = module_info[ANA_OUT]

            if module_index in modules_to_read:
                read_table.append(
                    {
                        DIGI_IN: None,
                        DIGI_OUT: None,
                        ANA_IN: None,
                        ANA_OUT: None,
                        READING_TYPE: module_info[READING_TYPE],
                        READING_INFO: module_info[READING_INFO],
                    }
                )

                if n_digi_in > 0:
                    read_table[-1][DIGI_IN] = (total_digi_in, n_digi_in)
                if n_digi_out > 0:
                    read_table[-1][DIGI_OUT] = (total_digi_out, n_digi_out)
                if n_ana_in > 0:
                    read_table[-1][ANA_IN] = (total_ana_in, n_ana_in)
                if n_ana_out > 0:
                    read_table[-1][ANA_OUT] = (total_ana_out, n_ana_out)

            total_digi_in += n_digi_in
            total_digi_out += n_digi_out
            total_ana_in += n_ana_in
            total_ana_out += n_ana_out

        if total_digi_in > 0:
            digi_in_reading = self.client.read_coils(0, total_digi_in)
        if total_digi_out > 0:
            digi_out_reading = self.client.read_coils(0x200, total_digi_out)
        if total_ana_in > 0:
            ana_in_reading = self.client.read_input_registers(0, total_ana_in * "H")
        if total_ana_out > 0:
            ana_out_reading = self.client.read_input_registers(
                0x200, total_ana_in * "H"
            )

        for module_read_table in read_table:
            readings = []

            try:
                i, n = module_read_table[DIGI_IN]
            except Exception:
                readings.append(None)
            else:
                readings.append(tuple(digi_in_reading[i : i + n]))

            try:
                i, n = module_read_table[DIGI_OUT]
            except Exception:
                readings.append(None)
            else:
                readings.append(tuple(digi_out_reading[i : i + n]))

            try:
                i, n = module_read_table[ANA_IN]
            except Exception:
                readings.append(None)
            else:
                raw_values = ana_in_reading[i : i + n]
                if not convert_values:
                    readings.append(raw_values)
                elif module_read_table[READING_TYPE] == "ssi":
                    readings.append(
                        tuple(self._read_value(raw_values, module_read_table))
                    )
                else:
                    readings.append(
                        tuple(
                            (self._read_value(x, module_read_table) for x in raw_values)
                        )
                    )

            try:
                i, n = module_read_table[ANA_OUT]
            except Exception:
                readings.append(None)
            else:
                raw_values = ana_out_reading[i : i + n]
                if not convert_values:
                    readings.append(raw_values)
                else:
                    readings.append(
                        tuple(
                            (self._read_value(x, module_read_table) for x in raw_values)
                        )
                    )

            ret.append(tuple(readings))

        return tuple(ret)

    def get(self, *channel_names, convert_values=True):
        """
        Read one or more values from channels
        Args:
            *channel_names (list): list of channels to be read
        Returns:
            (list): channel values
        """
        MODULE_NUM, IOTYPE, MOD_INT_CHANNEL = (0, 1, 2)

        ret = []

        channels_to_read = self.modules_config._resolve_read(*channel_names)

        # get the module number taking the first element of sub lists
        # for example: [[(0, 2, 0), (0, 2, 1)], [(2, 2, 1)], [(6, 2, 1)]] - > this gives [0, 2, 6]
        modules_to_read_list = sorted(
            set({module[0][0] for module in channels_to_read})
        )

        # read from the wago
        with self.lock:
            readings = self.read_phys(
                modules_to_read_list, convert_values=convert_values
            )
        if not readings:
            return None

        # deal with read values
        for channel_to_read in channels_to_read:
            values = []
            for i, j, k in channel_to_read:
                i = modules_to_read_list.index(i)
                values.append(readings[i][j][k])
            if len(channel_to_read) > 1:
                ret.append(values)
            else:
                ret += values

        # return a list with all the channels
        if not ret:
            return None
        if len(ret) == 1:
            return ret[0]

        # ret represents a list of lists, containing Wago values
        # by Wago module, but we prefer to have a flat list
        return flatten(ret)

    def _write_fs(self, value, low=0, high=10, base=32768):
        return int(((value - low) * base / float(high))) & 0xffff

    def write_phys(self, write_table):
        # write_table is a dict of module_index:
        # [(type_index, channel_index, value_to_write), ...]
        for module_index, write_info in write_table.items():
            module_info = get_module_info(
                self.modules_config.attached_modules[module_index]
            )
            for type_index, channel_index, value2write in write_info:
                if type_index == DIGI_OUT:
                    addr = (
                        self.modules_config.mapping[module_index]["writing_info"][
                            DIGI_OUT
                        ]
                        + channel_index
                    )
                    self.client.write_coil(addr, bool(value2write))
                elif type_index == ANA_OUT:
                    addr = (
                        self.modules_config.mapping[module_index]["writing_info"][
                            ANA_OUT
                        ]
                        + channel_index
                    )
                    writing_type = module_info[READING_TYPE]
                    if writing_type == "fs":
                        write_value = self._write_fs(
                            value2write, **module_info[READING_INFO]
                        )
                    else:
                        raise RuntimeError("Writing %r is not supported" % writing_type)
                    self.client.write_register(addr, "H", write_value)

    def set(self, *args):
        """Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        write_table = self.modules_config._resolve_write(*args)

        with self.lock:
            return self.write_phys(write_table)

    def devwritephys(self, array_in):
        name = self.devkey2name(array_in[0])
        self.set(flatten([name] + list(array_in[1:])))

    def devwritedigi(self, array_in):
        self.devwritephys(array_in)

    def devreadnocachedigi(self, key):
        # Doing a digital read on an analog channel gives the raw bit value (not converted in voltage, temperature ...)
        # convert_values=False forces this raw reading
        val = self.get(self.devkey2name(key), convert_values=False)

        # TODO: there are modules with 24 and 32 bit values, behaviour should be check

        def to_signed(num):
            # convert a 16 bit number to a signed representation
            if num >> 15:  # if is negative
                calc = -((num ^ 0xffff) + 1)  # 2 complement
                return calc
            return num

        # needed a conversion to fit the DevShort which is signed
        values = [to_signed(v) for v in flatten([val])]

        return values

    def devreaddigi(self, key):
        return self.devreadnocachedigi(key)

    def devreadnocachephys(self, key):
        val = self.get(self.devkey2name(key))
        return flatten([val])

    def devreadphys(self, key):
        return self.devreadnocachephys(key)

    def devkey2name(self, key):
        """
        From a key (channel enumeration) to the assigned text name

        Example:
            >>> DevKey2Name(3)
            b"gabsTf3"
        """
        try:
            inv_map = {v: k for k, v in self.modules_config.logical_keys.items()}
            return inv_map[key]
        except IndexError:
            raise Exception("invalid logical channel key")

    def devname2key(self, name):
        """From a logical device (name) to the key"""
        return self.modules_config.logical_keys[name]

    def devwccomm(self, args):
        """
        Send an command to Wago using the Interlock protocol

        Note: as the logic was implemented through reverse engineering there may be inaccuracie.
        """
        log_debug(self, f"In devwccomm args: {args}")
        command, params = args[0], args[1:]
        MAX_RETRY = 3
        SLEEP_TIME = 0.01

        """
        PHASE 1: Handshake protocol: starts with PASSWD=0

        Description:
        Write 0x0000 at holding register 0x0100
        """

        addr, data = 0x100, 0x0000  # WC_PASSWD, 0

        log_debug(
            self, f"devwccomm Phase 1: writing at address {addr:04X} value {data:04X}"
        )
        response = self.client.write_register(addr, "H", data, timeout=self.timeout)

        """
        PHASE 2: Handshake protocol: wait for OUTCMD==0

        Description: Read n.3 holding registers from address 0x0100

        Example of correct response:

        |  0xaa 0x01 | 0x0000 | 0x0000 |

        The code checks the first byte (version tag) that should be 0xaa
        and the last register that should be 0 (ACK)
        """

        addr, size = 0x100, 3

        log_debug(
            self, f"devwccomm Phase 2: reading at address {addr:04X} n.{size} registers"
        )

        start = time.time()
        while True:
            if time.time() - start > self.timeout * MAX_RETRY:
                raise TimeoutError("ACK not received")
            try:
                check, _, ack = self.client.read_input_registers(
                    addr, "H" * size, timeout=self.timeout
                )

            except Exception as exc:
                log_exception(self, f"failed to read at address: {addr} words: {size}")
                raise

            if (check >> 8) != 0xaa:  # check Version Tag
                log_debug(
                    self,
                    f"Invalid Wago controller program version: 0x{check>>8:02X} != 0xaa",
                )
                raise MissingFirmware("No interlock software loaded in the PLC")
            if ack == 0:  # check if is ok
                log_debug(self, "devwccomm Phase 2: ACK received")
                break
            else:
                gevent.sleep(SLEEP_TIME)

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
        gevent.sleep(0.1)  # needed delay otherwise we will receive part of old message
        try:
            check, error_code, command_executed, registers_to_read = self.client.read_input_registers(
                addr, "H" * size, timeout=self.timeout
            )
        except Exception as exc:
            log_debug(
                self,
                f"devwccomm Phase 4: failed to read at address: {addr} words: {size}",
            )
            raise
        # ERROR CHECK
        if (
            error_code != 0
        ):  # or command_executed != 0x04:  # 0x04 is the modbus command
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

        """
        PHASE 5: Read response

        Description: read registers starting from 0x104, the number of regs comes from PHASE 4
        """

        addr = 0x104
        size = registers_to_read
        log_debug(self, f"devwccomm Phase 5: reading at address: {addr} words: {size}")

        if size:
            try:
                response = self.client.read_input_registers(
                    addr, "H" * size, timeout=self.timeout
                )
                if isinstance(response, int):  # single number
                    response = [response]
                log_debug(self, f"read registers response={response}")
            except Exception as exc:
                log_exception(
                    self,
                    f"devwccomm Phase 5: failed to read at address: {addr} words: {size}",
                )
                raise
            # return [to_signed(n) for n in response]
            return response

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
        >>> wago.set_mapping(mapping)

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

    def print_plugged_modules(self):
        print(self._plugged_modules())

    def _plugged_modules(self):
        try:
            return self.__plugged_modules
        except AttributeError:
            pass
        try:
            modules = self.client.read_holding_registers(0x2030, "65H")
        except Exception as exc:
            log_exception(self, f"Can't retrieve Wago plugged modules {exc}")
            raise

        out = ""
        for i, m in enumerate(modules, -1):
            if not m:
                break
            if m & 0x8000:  # digital in/out
                direction = "Input" if m & 0x1 else "Output"
                mod_size = (m & 0xf00) >> 8
                out += f"module{i}: I/O mod ({mod_size} Channel digital {direction})\n"
            else:
                description = get_module_info(f"750-{m}")[DESCRIPTION]
                out += f"module{i}: 750-{m} ({description})\n"
        self.__plugged_modules = out
        return self.__plugged_modules

    @property
    def logical_mapping(self):
        return self.modules_config.logical_mapping

    @property
    def physical_mapping(self):
        return self.modules_config.physical_mapping

    @property
    def logical_keys(self):
        return self.modules_config.logical_keys

    @staticmethod
    def _check_mapping(module, register):
        """Checks if the given register value coresponds to the PLC type of module given

        Args:
            module (str): name of the module (E.G. '750-462')
            register (int): value obtained by modbus request on PLC that contains module
                            informations
        Return:
            True if modules corresponds to register info
            False if modules do not corresponds to registers info
        """
        if register & 0x8000:  # digital in/out
            isinput = True if register & 0x1 else False
            mod_size = (register & 0xf00) >> 8

            digi_in, digi_out, _, _, total, type_ = get_module_info(module)[:6]

            if (
                bool(digi_in)
                and isinput
                or bool(digi_out)
                and not isinput
                and (
                    (isinput and mod_size == digi_in)
                    or (not isinput and mod_size == digi_out)
                )
                and type_ == "digital"
            ):
                return True

        else:
            # all other modules
            if f"750-{register}" == module:
                return True
            if "750-562-UP" == module and register == 562:
                return True
        return False

    def check_plugged_modules(self):
        try:
            registers = self.client.read_holding_registers(0x2030, "65H")
        except Exception as exc:
            log_exception(self, f"Can't retrieve Wago plugged modules {exc}")
            raise

        for i, module in enumerate(self.modules_config.modules):
            # exclude the CPU main module
            if not WagoController._check_mapping(module, registers[i]):
                raise RuntimeError(
                    f"PLC addon module n.{i} (starting from zero) does not corresponds to mapping:{module}"
                )


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


class Wago:
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
        self.name = name

        # parsing config_tree
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

        from bliss.comm.util import get_comm

        # instantiating comm and controller class
        if config_tree["modbustcp"]["url"].startswith("tango://"):
            tango_url = config_tree["modbustcp"]["url"]
            if not len(self.modules_config.attached_modules):
                # if no config is provided for DeviceProxy get tango property
                mapping = tango.DeviceProxy(tango_url).get_property("config")["config"]
                self.modules_config = ModulesConfig.from_tango_config(mapping)
            self.controller = TangoWago(tango_url, self.modules_config)

        elif config_tree.get("simulate"):

            # launch the simulator
            from tests.conftest import get_open_ports
            from tests.emulators.wago import WagoMockup

            self.__mockup = WagoMockup(self.modules_config)
            # create the comm
            conf = {"modbustcp": {"url": f"localhost:{self.__mockup.port}"}}
            comm = get_comm(conf)
            self.controller = BlissWago(comm, self.modules_config)
            self.controller.connect()

        else:
            comm = get_comm(config_tree)
            self.controller = BlissWago(comm, self.modules_config)
            self.controller.connect()

        global_map.register(self, parents_list=["wago"], tag=f"Wago({self.name})")

        from bliss.controllers.wago.interlocks import beacon_interlock_parsing

        try:
            self._interlocks_on_beacon = beacon_interlock_parsing(
                config_tree["interlocks"], self.modules_config
            )
        except KeyError:
            # no interlock is defined on beacon or configuration mistake
            pass

    def __info__(self):
        """
        Returns:
            (tuple): names of logical keys
        """
        mapping = [
            (k, len(ch)) for k, ch in self.modules_config.logical_mapping.items()
        ]
        repr_ = "Wago PLC\n"
        for k, l in mapping:
            repr_ += f"logical device {k} has {l} channels\n"
        return repr_

    def close(self):
        self.controller.close()
        try:
            self.__mockup.close()
        except AttributeError:
            pass

    def __close__(self):
        self.close()

    def interlock_show(self):
        from bliss.controllers.wago.interlocks import interlock_download as download
        from bliss.controllers.wago.interlocks import interlock_show as show
        from bliss.controllers.wago.interlocks import interlock_compare as compare

        on_plc, on_beacon = False, False

        print_formatted_text(HTML(f"Interlocks on <violet>{self.name}</violet>"))
        try:
            self._interlocks_on_plc = download(self.controller, self.modules_config)
            on_plc = True
        except (MissingFirmware, tango.DevFailed):
            print("Interlock Firmware is not present in the PLC")

        try:
            self._interlocks_on_beacon
            on_beacon = True
        except AttributeError:
            print("Interlock configuration is not present in Beacon")

        if on_beacon and on_plc:
            # if configuration is present on both beacon and plc
            are_equal, messages = compare(
                self._interlocks_on_beacon, self._interlocks_on_plc
            )
            if are_equal:
                print_formatted_text(HTML("<green>On PLC:</green>"))
                print(show(self.name, self._interlocks_on_plc))
            else:
                print_formatted_text(HTML("<green>On PLC:</green>"))
                print(show(self.name, self._interlocks_on_plc))
                print_formatted_text(HTML("\n<green>On Beacon:</green>"))
                print(show(self.name, self._interlocks_on_beacon))
                print("There are configuration differences:")
                for line in messages:
                    print(line)
        else:
            if on_plc:
                print_formatted_text(HTML("<green>On PLC:</green>"))
                print(show(self.name, self._interlocks_on_plc))
            if on_beacon:
                print_formatted_text(HTML("\n<green>On Beacon:</green>"))
                print(show(self.name, self._interlocks_on_beacon))

    def interlock_reset_relay(self, instance_num):
        from bliss.controllers.wago.interlocks import interlock_reset as reset

        reset(self.controller, instance_num)

    def interlock_upload(self):
        from bliss.controllers.wago.interlocks import interlock_compare as compare
        from bliss.controllers.wago.interlocks import interlock_upload as upload
        from bliss.controllers.wago.interlocks import interlock_download as download

        self._interlocks_on_plc = download(self.controller, self.modules_config)
        are_equal, messages = compare(
            self._interlocks_on_beacon, self._interlocks_on_plc
        )
        if are_equal:
            print("No need to upload the configuration")
        else:
            yes_no = input(
                "Are you sure that you want to upload a new configuration? (Answer YES to proceed)"
            )
            if yes_no == "YES":
                upload(self.controller, self._interlocks_on_beacon)
                # double check
                self._interlocks_on_plc = download(self.controller)
                are_equal, messages = compare(
                    self._interlocks_on_beacon, self._interlocks_on_plc
                )
                if are_equal:
                    print("Configuration succesfully upload")
                else:
                    print("Something gone wrong: configurations are not the same")

    def _safety_check(self, *args):
        return True

    @synchronized()
    def set(self, *args, **kwargs):
        if not self._safety_check(*args):
            return
        if self.controller is None:
            self.connect()
        return self.controller.set(*args, **kwargs)

    @synchronized()
    def get(self, *args, **kwargs):
        # if self.controller is None:
        #    self.connect()
        return self.controller.get(*args, **kwargs)

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
