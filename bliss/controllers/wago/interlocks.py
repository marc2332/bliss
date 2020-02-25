# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import yaml

from collections import namedtuple
from itertools import zip_longest
import decimal

from typing import Union

from bliss.common.logtools import log_debug, log_info

from bliss.controllers.wago.helpers import (
    splitlines,
    remove_comments,
    word_to_2ch,
    bytestring_to_wordarray,
    to_unsigned,
    to_signed,
    pretty_float,
    register_type_to_int,
)
from bliss.controllers.wago.wago import (
    TangoWago,
    ModulesConfig,
    WagoController,
    get_module_info,
)


TYPES = {
    "IB": "Input bit",  # digital = 0b1 input = 0b00
    "OB": "Output bit",  # 3
    "IW": "Input word",  #
    "OW": "Output word",
    "TC": "Termocouple",  # 8 # scale = 0.1
    "IV": "10V input",
    "OV": "10V output",
}

COMMANDS = {
    "NAME": 0x0001,
    "ACTIVE": 0x0002,
    # checks if interlock is present in the PLC
    # request is (0x2, 0x0100)
    # response is ( free_inst, available_inst, imsk?)
    # registered_inst = available_inst - free_inst  # configured instances
    "RESET": 0x0003,
    "VERSION": 0x0004,
    "INTERLOCK": 0x0100,  # 256
    "ILCK_CREATE": 0x0101,  # 257
    "ILCK_DELETE": 0x0102,  # 258
    "ILCK_ADDCHAN": 0x0103,  # 259
    "ILCK_DELCHAN": 0x0104,  # 260
    "ILCK_GETCONF": 0x0105,
    # (261, 1)  asks for the configuration of the first interlock (starting from 1)
    # Response ( offset, flags , total number of channels on the interlock)
    #
    # (261, 1, 1) asks for configuration of first channel of first interlock (starting from 1)
    # Response length:
    #                   - is 3 if is a digital channel (can be of type IB or OB)
    #                      (flags, offset, actual value)
    #
    #                   - is 5 if is an analog channel
    #                      (flags, offset, low limit, high limit, type, actual value)
    #                      Example ( 8, 0, 0, 500, 21571, 235)
    #
    # NOTE: type is a word that is split in two bytes and coresponds to ascii of types
    #       for example word_to_2ch(21571) gives 'TC' which is TermoCoupler type
    #
    # TODO:
    #       monitor flag: (we will have 5 more values)
    #       if flags & flg["cbit"]["monitor"]) :
    #           first is "dac"
    #           second+third is "dac_scale"  32bit value
    #           fourth+fifth is "dac_offset" 32bit value
    #
    "ILCK_SETNAME": 0x0106,  # 262
    "ILCK_GETNAME": 0x0107,  # 263
    # 263,2 the answer is the ascii description given as an array of words
    # the maximum size of description seems to be 32 chars (TODO: check this)
    "ILCK_GETSTAT": 0x0108,  # 264
    # first value & STMASK will result in status, second value is VALUE
    # Example: 264,1 asks for state of interlock 1
    "ILCK_SETFLGS": 0x0109,  # 265
    "ILCK_CLRFLGS": 0x010A,  # 266
    "ILCK_SETTHR": 0x010B,  # 267
    "ILCK_RESET": 0x010C,  # 268
    # 268,4 resets interlock n.4
    # Can return an error code
}

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

FLAGS = {
    "tbit": {
        "digital": 0x0001,
        "output": 0x0002,
        "DIGITAL": 0x0001,
        "OUTPUT": 0x0002,
        "input": 0x0,
        "analog": 0x0,
        "INPUT": 0x0,
        "ANALOG": 0x0,
    },  # type bit
    # input and analog added for compatibility
    "cbit": {  # configuration bit
        "unsigned": 0x0004,
        "sticky": 0x0008,
        "STICKY": 0x0008,
        "inverted": 0x0010,  # 16
        "INVERTED": 0x0010,  # 16
        "inv": 0x0010,  # 16
        "INV": 0x0010,
        "disabled": 0x0020,  # 32
        "DISABLED": 0x0020,
        "monitor": 0x0040,  # 64
        "MONITOR": 0x0040,
        "mon": 0x0040,
        "noforce": 0x0080,  # 128
        "NOFORCE": 0x0080,
    },
    "sbit": {  # status bit
        "tripped": 0x0100,  # 256
        "alarm": 0x0200,
        "cfgerr": 0x0400,  # 1024
        "hdwerr": 0x0800,  # 2048
    },
}


InterlockState = namedtuple("InterlockState", "tripped alarm cfgerr hdwerr")


def is_digital(flags):
    return bool(flags & 0b1)


def is_analog(flags):
    return not is_digital(flags)


def is_output(flags):
    return bool(flags & 0b10)


def is_input(flags):
    return not is_output(flags)


def is_unsigned(flags):
    return bool(flags & FLAGS["cbit"]["unsigned"])


def is_sticky(flags):
    return bool(flags & FLAGS["cbit"]["sticky"])


def is_inverted(flags):
    return bool(flags & FLAGS["cbit"]["inverted"])


def is_noforce(flags):
    return bool(flags & FLAGS["cbit"]["noforce"])


def is_disabled(flags):
    return bool(flags & FLAGS["cbit"]["disabled"])


def is_monitor(flags):
    return bool(flags & FLAGS["cbit"]["monitor"])


def is_tripped(flags):
    return bool(flags & FLAGS["sbit"]["tripped"])


def is_alarm(flags):
    return bool(flags & FLAGS["sbit"]["alarm"])


def is_cfgerr(flags):
    return bool(flags & FLAGS["sbit"]["cfgerr"])


def is_hdwerr(flags):
    return bool(flags & FLAGS["sbit"]["hdwerr"])


mask = {
    "IMASK": 0x0098,  # instance:  inverted + sticky + noforce  # 152
    "TCHMASK": 0x0003,  # channel type:  digital + output  # 3
    "BCHMASK": 0x0038,  # bits:  sticky + inverted + disabled  # 56
    "WCHMASK": 0x007c,  # words: unsigned + sticky + inverted + disabled + monitor# 124
    "STMASK": 0xff00,  # status: trip + alarm + cfgerr + hdwerr
}


def imask(flags: int):
    return flags & mask["IMASK"]  # instance:  inverted + sticky + noforce  # 152


def tchmask(flags: int):
    return flags & mask["TCHMASK"]  # channel type:  digital + output  # 3


def bchmask(flags: int):
    return flags & mask["BCHMASK"]  # bits:  sticky + inverted + disabled  # 56


def wchmask(flags: int):
    return (
        flags & mask["WCHMASK"]
    )  # words: unsigned + sticky + inverted + disabled + monitor# 124


def stmask(flags: int):
    return flags & mask["STMASK"]  # status: trip + alarm + cfgerr + hdwerr


def string_to_flags(flags_str: Union[str, None]):
    # convert from string to boolean flags
    flags = 0
    if flags_str is not None:
        for flag in flags_str.split():
            flags += {**FLAGS["tbit"], **FLAGS["cbit"], **FLAGS["sbit"]}[flag]
    return flags


def flags_to_string(flags: int):
    """convert from flags to string
    Args:
        flags (int): all flags in a single integer

    Returns:
        str: single string with all represented flags

    Examples:

        >>> flags_to_str(0x18)
        "STICKY INVERTED"
    """
    states = {
        0x1: "DIGITAL",
        0x2: "OUTPUT",
        0x4: "UNSIGNED",
        0x8: "STICKY",
        0x10: "INVERTED",
        0x20: "DISABLED",
        0x40: "MONITOR",
        0x80: "NOFORCE",
        0x100: "TRIPPED",
        0x200: "ALARM",
        0x400: "CFGERR",
        0x800: "HDWERR",
    }

    current_states = []
    for fl, st in states.items():
        if flags & fl:
            current_states.append(st)
    return " ".join(current_states)


cfgarr = {"filename": None}


def interlock_parse_relay_line(line):
    """
    Syntax:
        relay <outrelay1> {<iflag> ... } [name <name_string>]
    Notes:
        - <outrelay> must be a digital output channel
        - Instance flags (<iflag>): inverted, sticky, noforce
        - comment are not processed and should be removed before with `remove_comments`
    """
    regex_relay_line = r"\s*relay +(?P<relay>[a-zA-Z0-9_]+)(\[(?P<channel>[0-9])\])?( +(?P<iflags>(inverted|inv|INV|INVERTED|sticky|STICKY|noforce|NOFORCE| )+))?( +name +(?P<description>[a-zA-Z0-9_ -\/]+))?$"
    m = re.match(regex_relay_line, line)
    ParsedRelayLine = namedtuple(
        "ParsedRelayLine", "logical_device logical_device_channel flags description"
    )
    if m:
        line = ParsedRelayLine(
            m["relay"],
            0 if m["channel"] is None else int(m["channel"]),
            string_to_flags(m["iflags"]),
            "" if m["description"] is None else m["description"],
        )
        return line
    return None


ParsedChannelLine = namedtuple(
    "ParsedChannelLine",
    "logical_device logical_device_channel type low_limit high_limit flags dac dac_scale dac_offset",
)


def interlock_parse_channel_line(line):
    """
    Syntax:
        <chan1> <type> [<min> <max>] {<chflag> ... }
        <chan2> <type> [<min> <max>] {<chflag> ... }
            ...
        <chanN> <type> [<min> <max>] {<chflag> ... }

    Notes:
        - Channel types (<type>) supported: IB, OB, IW, OW, TC, IV, OV
        - <min> <max> values are required for word (analog) values
        - Channel flags <chflag>: inverted, sticky
        - Channels should be specified with logical names with subarray syntax
        - comment are not processed and should be removed before with `remove_comments`
    """
    regex_control_ch_line = (
        r"\s*(?P<logical_name>[a-zA-Z0-9_+-]+)(\[(?P<channel>[0-9]+)\])?\s+(?P<type>"
        + r"|".join(TYPES.keys())
        + r")( +(?P<min>\-?[0-9\.]+))?( +(?P<max>\-?[0-9\.]+))?( +(?P<chflags>(inverted|inv|INV|INVERTED|sticky|STICKY|monitor|MONITOR| )*))?"
    )
    regex_control_ch_line += r"( +(?P<dac>[a-zA-Z0-9_+-]+) +(?P<dac_scale>[0-9-\.]+) +(?P<dac_offset>[0-9]+))?$"

    m = re.match(regex_control_ch_line, line)

    if m:
        type_flags = 0
        # setting proper type flag
        if m["type"] not in TYPES.keys():
            raise RuntimeError("Type not recognized")
        if m["type"] in ("OB", "OW", "OV"):
            type_flags |= FLAGS["tbit"]["output"]
        if m["type"] in ("IB", "OB"):
            type_flags |= FLAGS["tbit"]["digital"]
        min_ = float(m["min"]) if m["min"] else None
        max_ = float(m["max"]) if m["max"] else None

        line = ParsedChannelLine(
            m["logical_name"],
            0 if m["channel"] is None else int(m["channel"]),
            m["type"],
            min_,
            max_,
            string_to_flags(m["chflags"]) | type_flags,
            m["dac"],
            float(m["dac_scale"]) if m["dac_scale"] is not None else None,
            int(m["dac_offset"]) if m["dac_offset"] is not None else None,
        )
        return line


def beacon_interlock_parsing(yml, modules_config: ModulesConfig):
    interlock_list = []
    for num, node in enumerate(yml, 1):
        logical_device = node["relay"]
        logical_device_channel = node.get("relay_channel", 0)
        flags = string_to_flags(node.get("flags", "") + " DIGITAL")
        description = node.get("description", "")[:32]  # trim size

        logical_device_key = modules_config.devname2key(logical_device)

        interlock_list.append(
            _interlock_relay_info(
                num,
                description,
                flags,
                logical_device,
                logical_device_key,
                logical_device_channel,
            )
        )

        for channel in node["channels"]:
            type_flags = 0
            # setting proper type flag
            if channel["type"] not in TYPES.keys():
                raise RuntimeError("Type not recognized")
            if channel["type"] in ("OB", "OW", "OV"):
                type_flags |= FLAGS["tbit"]["output"]
            if channel["type"] in ("IB", "OB"):
                type_flags |= FLAGS["tbit"]["digital"]

            chflags = string_to_flags(channel.get("flags", "")) | type_flags

            parsed = ParsedChannelLine(
                channel["logical_name"],
                channel.get("logical_channel", 0),
                channel["type"],
                channel.get("min"),
                channel.get("max"),
                chflags,
                channel.get("dac"),
                channel.get("dac_scale"),
                channel.get("dac_offset"),
            )
            ch_num = len(interlock_list[-1]["channels"]) + 1
            interlock_list[-1]["channels"].append(
                _interlock_channel_info_from_parsed(ch_num, parsed, modules_config)
            )
    return interlock_list


def specfile_interlock_parsing(iterable, modules_config: ModulesConfig):
    interlock_list = []
    for line in remove_comments(splitlines(iterable)):
        if line:
            if interlock_parse_relay_line(line) is not None:
                num = len(interlock_list) + 1
                logical_device, logical_device_channel, iflags, description = interlock_parse_relay_line(
                    line
                )
                logical_device_key = modules_config.devname2key(logical_device)
                flags = iflags

                interlock_list.append(
                    _interlock_relay_info(
                        num,
                        description,
                        flags,
                        logical_device,
                        logical_device_key,
                        logical_device_channel,
                    )
                )

            elif interlock_parse_channel_line(line):
                ch_num = len(interlock_list[-1]["channels"]) + 1
                interlock_list[-1]["channels"].append(
                    _interlock_channel_info_from_parsed(
                        ch_num, interlock_parse_channel_line(line), modules_config
                    )
                )
            else:
                raise Exception(f"Can't interpret '{line}'")
    return interlock_list


def specfile_to_yml(iterable):
    """Converts an iterable derived from a spec file containing interlock informations
    to a yml equivalent to be used on beacon"""

    yml = {"interlocks": []}
    for line in remove_comments(splitlines(iterable)):
        if interlock_parse_relay_line(line) is not None:
            r = interlock_parse_relay_line(line)
            r_y = {"relay": r.logical_device}

            flags = flags_to_string(imask(r.flags))
            if flags:
                r_y["flags"] = flags
            if r.logical_device_channel:
                r_y["logical_channel"] = r.logical_device_channel
            if r.description:
                r_y["description"] = r.description
            r_y["channels"] = []

            yml["interlocks"].append(r_y)

        elif interlock_parse_channel_line(line) is not None:
            c = interlock_parse_channel_line(line)
            c_y = {"logical_name": c.logical_device, "type": c.type}

            flags = flags_to_string(bchmask(c.flags))
            if flags:
                c_y["flags"] = flags
            if c.low_limit is not None:
                c_y["min"] = pretty_float(c.low_limit)
            if c.high_limit is not None:
                c_y["max"] = pretty_float(c.high_limit)
            if c.dac is not None:
                c_y["dac"] = c.dac
            if c.dac_scale is not None:
                c_y["dac_scale"] = c.dac_scale
            if c.dac_offset is not None:
                c_y["dac_offset"] = c.dac_offset
            yml["interlocks"][-1]["channels"].append(c_y)

    return yaml.dump(yml, default_flow_style=False, sort_keys=False)


def interlock_to_yml(interlock_list):
    """Converts a configuration to yml
    Useful if you download a configuration from the PLC
    and create from this a valid Beacon yaml file
    """
    d_i = {"interlocks": []}
    for intrlck in interlock_list:
        r_d = {
            "relay": intrlck["logical_device"],
            "relay_channel": int(intrlck["logical_device_channel"]),
            "flags": flags_to_string(imask(intrlck["flags"])),
            "description": intrlck["description"],
            "channels": [],
        }
        for ch in intrlck["channels"]:
            c_d = {
                "logical_name": ch["logical_device"],
                "logical_channel": ch["logical_device_channel"],
                "type": ch["type"]["type"],
                "flags": flags_to_string(wchmask(ch["flags"])),
            }
            if ch["low_limit"] is not None:
                c_d["min"] = float(
                    round(decimal.Decimal(to_signed(int(ch["low_limit"]))) / 10, 2)
                )
            if ch["high_limit"] is not None:
                c_d["max"] = float(
                    round(decimal.Decimal(to_signed(int(ch["high_limit"]))) / 10, 2)
                )
            for name in "dac_scale dac_offset".split():
                if ch[name] is not None:
                    c_d[name] = ch[name]
            r_d["channels"].append(c_d)
        d_i["interlocks"].append(r_d)

    return yaml.dump(d_i, default_flow_style=False, sort_keys=False)


def _interlock_relay_info(
    num, description, flags, logical_device, logical_device_key, logical_device_channel
):
    """
    Args:
        num (int): progressive number of interlock
        description (str): description of relay
        flags (int): flags
        logical_device (str): name of output device (E.G. relaymono)
        logical_device_key (int): logical device key
        logical_device_channel (int): logical device channel
    """
    info = {
        "num": num,
        "description": description.strip("\0")[:32],  # max size 32
        "logical_device": logical_device,
        "logical_device_key": logical_device_key,
        "logical_device_channel": logical_device_channel,
        "value": None,
        "flags": flags,
        "settings": {
            "inverted": is_inverted(flags),
            "sticky": is_sticky(flags),
            "noforce": is_noforce(flags),
        },
        "status": {
            "tripped": is_tripped(flags),
            "alarm": is_alarm(flags),
            "hdwerr": is_hdwerr(flags),
            "cfgerr": is_cfgerr(flags),
        },
        "channels": [],
    }
    return info


def _interlock_channel_info_from_plc(
    num, get_conf_output, modules_config: ModulesConfig
):
    """
    Args:
        num: number of interlock
        get_conf_output:
    """
    flags = get_conf_output[0]
    offset = get_conf_output[1]
    value = get_conf_output[-1]  # actual value is last received

    info = {
        "num": num,
        "logical_device": None,
        "logical_device_key": None,
        "logical_device_channel": None,
        "value": value,
        "flags": flags,
        "type": {
            "digital": is_digital(flags),
            "output": is_output(flags),
            "type": None,
            "register_type": None,
            "scale": 1,
        },
        "configuration": {
            "unsigned": is_unsigned(flags),  # only for word channels
            "sticky": is_sticky(flags),  # both bit and word channels
            "inverted": is_inverted(flags),  # both bit and word channels
            "disabled": is_disabled(flags),  # both bit and word channels
            "monitor": is_monitor(flags),  # only for word channels
            "noforce": is_noforce(flags),  ##?????
        },
        "low_limit": None,
        "high_limit": None,
        "dac": None,
        "dac_scale": None,  # 32bit
        "dac_offset": None,  # 32bit
        "status": {
            "hdwerr": is_hdwerr(flags),
            "cfgerr": is_cfgerr(flags),
            "alarm": is_alarm(flags),
            "tripped": is_tripped(flags),
        },
    }
    if len(get_conf_output) == 3:
        if is_output(flags):
            info["type"]["type"] = "OB"
        else:
            info["type"]["type"] = "IB"

    if is_output(flags):
        if is_analog(flags):
            info["type"]["register_type"] = "OW"
        else:
            info["type"]["register_type"] = "OB"
    else:
        if is_analog(flags):
            info["type"]["register_type"] = "IW"
        else:
            info["type"]["register_type"] = "IB"

    if len(get_conf_output) > 3:
        info["low_limit"] = to_unsigned(get_conf_output[2], bits=16)
        info["high_limit"] = to_unsigned(get_conf_output[3], bits=16)
        info["type"]["type"] = word_to_2ch(get_conf_output[-2])
    if len(get_conf_output) > 6:  # TODO: check order of a dac
        info["dac"] = get_conf_output[5]
        info["dac_scale"] = get_conf_output[6]
        info["dac_offset"] = get_conf_output[7]

    logical_device_key, logical_device_channel = modules_config.devhard2log(
        (register_type_to_int(info["type"]["register_type"]), offset)
    )
    logical_device = modules_config.devkey2name(logical_device_key)

    info["logical_device"] = logical_device
    info["logical_device_key"] = logical_device_key
    info["logical_device_channel"] = logical_device_channel

    # scale information
    module_type = modules_config.read_table[logical_device][logical_device_channel][
        "module_reference"
    ]

    type_ = get_module_info(module_type).reading_type

    if info["type"]["type"] in ("IW", "OW"):
        # do not scale because we ask for raw values
        info["type"]["scale"] = 1
    elif module_type == "fs30":
        info["type"]["scale"] = 30  # check this
    elif type_ == "thc":
        info["type"]["scale"] = 10
    elif type_.startswith("fs"):
        info["type"]["scale"] = 0x8000 / 10

    return info


def _interlock_channel_info_from_parsed(num, parsed, modules_config: ModulesConfig):
    """
    Args:
        num: number of interlock
        get_conf_output (tuple):
            * case digital channel:
                (logical_device, logical_device_channel, type, flags)
                E.G. ('fire', 1, 'IB', None, None, 0)

            * case analog channel:
                (logical_device, logical_device_channel, type, min, max, flags)
                E.G. ('1stxtalsi111', 0, 'TC', -200, 55, 0)

            * case analog channel with dac:
                TODO:...
    """

    info = {
        "num": num,
        "logical_device": parsed.logical_device,
        "logical_device_key": None,
        "logical_device_channel": parsed.logical_device_channel,
        "value": None,
        "flags": parsed.flags,
        "type": {
            "digital": is_digital(parsed.flags),
            "output": is_output(parsed.flags),
            "type": parsed.type,
            "register_type": None,
            "scale": 1,
        },
        "configuration": {
            "unsigned": is_unsigned(parsed.flags),  # only for word channels
            "sticky": is_sticky(parsed.flags),  # both bit and word channels
            "inverted": is_inverted(parsed.flags),  # both bit and word channels
            "disabled": is_disabled(parsed.flags),  # both bit and word channels
            "monitor": is_monitor(parsed.flags),  # only for word channels
            "noforce": is_noforce(parsed.flags),  ##?????
        },
        "low_limit": None,
        "high_limit": None,
        "dac": None,
        "dac_scale": None,  # 32bit
        "dac_offset": None,  # 32bit
        "status": {
            "hdwerr": is_hdwerr(parsed.flags),
            "cfgerr": is_cfgerr(parsed.flags),
            "alarm": is_alarm(parsed.flags),
            "tripped": is_tripped(parsed.flags),
        },
    }

    if is_output(parsed.flags):
        if is_analog(parsed.flags):
            info["type"]["register_type"] = "OW"
        else:
            info["type"]["register_type"] = "OB"
    else:
        if is_analog(parsed.flags):
            info["type"]["register_type"] = "IW"
        else:
            info["type"]["register_type"] = "IB"

    # scale information
    module_type = modules_config.read_table[parsed.logical_device][
        parsed.logical_device_channel
    ]["module_reference"]

    type_ = get_module_info(module_type).reading_type

    if parsed.type in ("IW", "OW"):
        # do not scale because we ask for raw values
        scale = 1
    elif module_type == "fs30":
        scale = 30
    elif type_ == "thc":
        scale = 10
    elif type_.startswith("fs"):
        scale = 0x8000 / 10
    else:
        scale = 1

    info["type"]["scale"] = scale

    if info["type"]["type"] in ("TC", "IV", "OV"):
        # if we have those we should apply a conversion

        # converting to raw_values raw_value = (value * scale)
        info["low_limit"] = to_unsigned(int(parsed.low_limit * scale))
        info["high_limit"] = to_unsigned(int(parsed.high_limit * scale))
    elif info["type"]["type"] in ("OW", "IW"):
        # if we have those we do not appy conversion
        info["low_limit"] = to_unsigned(int(parsed.low_limit))
        info["high_limit"] = to_unsigned(int(parsed.high_limit))
    """
    # Not implemented parsing
    if is_monitor(parsed.flags):
        info["dac"] = parsed.dac
        info["dac_scale"] = parsed.dac_scale
        info["dac_offset"] = parsed.dac_offset
    """

    info["logical_device_key"] = modules_config.devname2key(parsed.logical_device)

    return info


def interlock_compare(int_list_1, int_list_2):
    """Compare two interlock lists,
    tipically used to compare file configuration with real configuration

    Returns a boolean set to True if the two lists are equal (from an interlock
    configuration perspective) and a list of messages concerning differences

    Args:
        int_list_1: list of interlocks (object _interlock_relay_info)
        int_list_2: list of interlocks (object _interlock_relay_info)

    Returns:
        tuple: ( bool, list of messages )
    """
    messages = []

    for int_1, int_2 in zip_longest(int_list_1, int_list_2):
        keys = "num logical_device logical_device_key logical_device_channel settings".split()

        num = int_1["num"] if int_1 is not None else int_2["num"]

        if int_1 is None or int_2 is None:
            messages.append(f"Interlock n.{num} is missing")
            continue

        for k in keys:
            if int_1[k] != int_2[k]:
                messages.append(
                    f"Configuration differs for {k}: {int_1[k]} != {int_2[k]}"
                )
        if bytestring_to_wordarray(int_1["description"]) != bytestring_to_wordarray(
            int_2["description"]
        ):
            messages.append(
                f"Interlock n.{num} for description: {int_1['description']} != {int_2['description']}"
            )

        if imask(int_1["flags"]) != imask(int_2["flags"]):
            messages.append(
                f"Interlock n.{num} for flags: {int_1['flags']} != {int_2['flags']}"
            )

        for ch1, ch2 in zip_longest(int_1["channels"], int_2["channels"]):

            ch_num = ch1["num"] if ch1 is not None else ch2["num"]

            if ch1 is None or ch2 is None:
                messages.append(
                    f"Channel n.{ch_num} on Interlock n.{int_1['num']} is missing"
                )
                continue

            ch_keys = "num logical_device logical_device_key logical_device_channel type configuration low_limit high_limit dac dac_scale dac_offset".split()
            for ck in ch_keys:
                val1, val2 = ch1[ck], ch2[ck]
                if val1 != val2:
                    # apply the scale to some values
                    if ck in ("low_limit", "high_limit"):  # ,"dac", "dac_scale"):
                        if isinstance(val1, (int, float)):
                            val1 = to_signed(val1)
                            scale1 = ch1["type"]["scale"]
                            try:
                                val1 = val1 / scale1  # better format
                            except Exception:
                                pass
                        if isinstance(val2, (int, float)):
                            val2 = to_signed(val2)
                            scale2 = ch2["type"]["scale"]
                            try:
                                val2 = val2 / scale2
                            except Exception:
                                pass

                    messages.append(
                        f"Interlock n.{num} channel n.{ch_num} for {ck}: {val1} != {val2}"
                    )
            if wchmask(ch1["flags"]) != wchmask(ch2["flags"]):
                messages.append(
                    f"Interlock n.{num} channel n.{ch_num} for flags: {ch1['flags']} != {ch2['flags']}"
                )

    return not bool(len(messages)), messages


def interlock_download(
    wago: Union[TangoWago, WagoController], modules_config: ModulesConfig
):
    """Downloads interlock configuration from wago

    Note: wago mapping should be set before calling this
    """
    log_info(wago, f"Checking interlock on Wago")

    registered_inst, available_inst, free_inst = interlock_memory(wago)

    interlock_list = []  # list containing all interlock dictionaries

    for i in range(1, registered_inst + 1):
        offset, flags, n_of_channels = wago.devwccomm((COMMANDS["ILCK_GETCONF"], i))

        # get istance description
        word_name = wago.devwccomm((COMMANDS["ILCK_GETNAME"], i))
        description = ""  # TODO: '\x00\x00 is not a proper response
        for word in word_name:
            description += word_to_2ch(word)
        description = description.strip("\0").strip()

        # getting state of relay
        status_flags, value = wago.devwccomm((COMMANDS["ILCK_GETSTAT"], i))
        flags |= stmask(status_flags)

        log_debug(
            wago,
            f"Wago interlock n.{i} with description {description} has {n_of_channels} n_of_channels, flags:{flags:b}",
        )
        logical_device_key, logical_device_channel = wago.devhard2log(
            (register_type_to_int("OB"), offset)
        )

        # relay channel name ( like pk_int[1] )
        logical_device = wago.devkey2name(logical_device_key)

        interlock_relay_info = _interlock_relay_info(
            i,
            description,
            flags,
            logical_device,
            logical_device_key,
            logical_device_channel,
        )
        interlock_relay_info["value"] = value

        log_debug(
            wago,
            f"Relay logical name={logical_device} inverted={is_inverted(flags)}, tripped={is_tripped(flags)}, noforce={is_noforce(flags)}",
        )
        log_debug(wago, "Is TRIPPED" if is_tripped(flags) else "Is NOT TRIPPED")

        for j in range(1, n_of_channels + 1):
            received = wago.devwccomm((COMMANDS["ILCK_GETCONF"], i, j))
            log_debug(wago, f"Wago interlock n.{i} channel n.{j} received {received}")
            flags = received[0]
            offset = received[1]

            if len(received) == 3:
                if is_output(flags):
                    register_type = "OB"
                else:
                    register_type = "IB"
            else:
                if is_output(flags):
                    register_type = "OW"
                else:
                    register_type = "IW"

            logical_device_key, logical_device_channel = wago.devhard2log(
                (register_type_to_int(register_type), offset)
            )
            interlock_channel_info = _interlock_channel_info_from_plc(
                j, received, modules_config
            )
            interlock_relay_info["channels"].append(interlock_channel_info)
        interlock_list.append(interlock_relay_info)
    return interlock_list


def interlock_state(wago: Union[TangoWago, WagoController]):
    log_info(wago, f"Checking interlock state on Wago")
    registered_inst, available_inst, free_inst = interlock_memory(wago)

    state_list = []

    for i in range(1, registered_inst + 1):
        # getting state of relay
        state_flags, value = wago.devwccomm((COMMANDS["ILCK_GETSTAT"], i))
        state = InterlockState(
            is_tripped(state_flags),
            is_alarm(state_flags),
            is_cfgerr(state_flags),
            is_hdwerr(state_flags),
        )

        state_list.append(state)
    return state_list


def interlock_purge(wago: Union[TangoWago, WagoController]):
    """Purges all interlocks available into a PLC"""
    log_info(wago, f"Interlock: Uploading interlock on Wago")

    free_inst, available_inst, imsk = wago.devwccomm(
        (COMMANDS["ACTIVE"], COMMANDS["INTERLOCK"])
    )
    registered_inst = available_inst - free_inst
    log_debug(wago, f"Interlock: Wago registered instances: {registered_inst}")

    # DELETE INSTANCES
    for i in range(1, registered_inst + 1):
        if imsk & 0b1:  # check first bit
            wago.devwccomm((COMMANDS["ILCK_DELETE"], i))  # deleting instance
        imsk >>= 1


def interlock_upload(wago: Union[TangoWago, WagoController], interlock_list: list):
    """
    Upload a list of interlocks on Wago

    Args:
        wago (WagoController): instance of Class
        interlock_list (list): list created by specfile_interlock_parsing or with beacon config
    """
    interlock_purge(wago)

    # CREATING INSTANCES

    for interlock in interlock_list:
        logical_device_key = interlock["logical_device_key"]
        logical_device_channel = interlock["logical_device_channel"]
        offset, _, _, _, _ = wago.devlog2hard(
            (logical_device_key, logical_device_channel)
        )
        response = wago.devwccomm((COMMANDS["ILCK_CREATE"], offset, interlock["flags"]))
        instance_number = response[0]

        # if size is less than 32 fill with spaces
        _description = interlock["description"][:32].ljust(32)

        description = bytestring_to_wordarray(_description)

        wago.devwccomm((COMMANDS["ILCK_SETNAME"], instance_number, *description))
        for channel in interlock["channels"]:
            logical_device_key, logical_device_channel = (
                channel["logical_device_key"],
                channel["logical_device_channel"],
            )
            offset, _, _, _, _ = wago.devlog2hard(
                (logical_device_key, logical_device_channel)
            )
            params = (instance_number, channel["flags"], offset)
            if not channel["type"]["digital"]:
                params += (channel["low_limit"], channel["high_limit"])
                type_ = channel["type"]["type"]
                params += ((ord(type_[0]) << 8) + ord(type_[1]),)
            # TODO: implement DAC

            response = wago.devwccomm((COMMANDS["ILCK_ADDCHAN"], *params))
            """
            if response[0] != offset + 1:
                log_error(wago, f"ILCK_ADDCHAN {params} should give {offset+1}")
                #raise RuntimeError(f"Wrong response from Wago Interlock {response}")
                """


def interlock_memory(wago):
    free_inst, available_inst, _ = wago.devwccomm(
        (COMMANDS["ACTIVE"], COMMANDS["INTERLOCK"])
    )
    registered_inst = available_inst - free_inst

    log_debug(
        wago,
        f"Wago interlock instances: registered={registered_inst} free={free_inst}, available={available_inst}",
    )
    return registered_inst, available_inst, free_inst


def interlock_reset(wago, instance_n):
    log_debug(wago, f"Interlock: Resetting instance n.{instance_n}")
    response = wago.devwccomm((COMMANDS["ILCK_RESET"], instance_n))  # deleting instance
    if response:
        raise RuntimeError(f"Interlock: Error response from PLC: {ERRORS[response[0]]}")


def interlock_show(wc_name: str, interlock_info: list):
    """Displays the interlock configuration
    stored in an interlock_data dictionary
    """

    out = f"{len(interlock_info)} interlock instance\n"

    for info in sorted(interlock_info, key=lambda i: i["num"]):
        num, description, logical_device, logical_device_channel = (
            info["num"],
            info["description"],
            info["logical_device"],
            info["logical_device_channel"],
        )
        channels = info["channels"]

        value = info["value"]
        if info["value"] is not None:  # None is the case of 'offline' representation
            value = "ON" if info["value"] else "OFF"
        else:
            value = None

        state = "TRIPPED" if info["status"]["tripped"] else "NOT TRIPPED"

        bchstring = flags_to_string(bchmask(info["flags"]))
        out += f"  Instance #{num}   Description: {description}\n"
        out += f"    Alarm relay = {logical_device}[{logical_device_channel}]  {bchstring}".ljust(
            68
        )
        out += f"[{value}]\n"
        out += f"    State = {state}\n"
        out += f"    {len(channels)} channels configured:\n"
        for ch in channels:
            ch_num = ch["num"]
            ch_hwerr = "H" if ch["status"]["hdwerr"] else "."
            ch_cfgerr = "C" if ch["status"]["cfgerr"] else "."
            ch_alarm = "A" if ch["status"]["alarm"] else "."
            ch_tripped = "T" if ch["status"]["tripped"] else "."
            logical_device = ch["logical_device"]
            type_ = ch["type"]["type"]
            scale = ch["type"]["scale"]

            if type_ in ("IW", "OW"):
                # print raw values
                ch_value = ch["value"] if ch["value"] else None
            else:
                ch_value = to_signed(ch["value"]) / scale if ch["value"] else None

            ch_logical_device = ch["logical_device"]
            chline = f"      #{ch_num:>2}  {ch_hwerr}{ch_cfgerr}{ch_alarm}{ch_tripped} - {logical_device}  {type_}  "

            if ch["type"]["digital"]:
                if ch["value"] is None:  # proper visualize 'offline' configurations
                    ch_value = None
                else:
                    ch_value = "ON" if ch["value"] else "OFF"
            else:
                low_limit = to_signed(ch["low_limit"]) / scale
                high_limit = to_signed(ch["high_limit"]) / scale
                if type_ in ("IW", "OW"):
                    # print raw values
                    chline += f"Low:{low_limit:.0f} High:{high_limit:.0f}"
                else:
                    chline += f"Low:{low_limit:.4f} High:{high_limit:.4f}"

            chline += "  STICKY" if ch["configuration"]["sticky"] else ""
            chline += "  INVERTED" if ch["configuration"]["inverted"] else ""

            out += chline.ljust(68) + f"[{ch_value}]\n"
        out += "\n"

    return out
