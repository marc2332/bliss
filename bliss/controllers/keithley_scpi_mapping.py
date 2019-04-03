# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from functools import partial

import numpy

from bliss.comm.scpi import Commands
from bliss.comm.scpi import COMMANDS as _COMMANDS
from bliss.comm.scpi import decode_IDN as _decode_IDN
from bliss.comm.scpi import (
    Cmd,
    ErrCmd,
    ErrArrayCmd,
    FuncCmd,
    OnOffCmd,
    BoolCmdRO,
    IntCmd,
    IntCmdRO,
    IntCmdWO,
    FloatCmd,
    FloatCmdRO,
    FloatCmdWO,
    StrCmd,
    StrCmdRO,
    StrCmdWO,
    StrArrayCmd,
    StrArrayCmdRO,
    IntArrayCmdRO,
)

# need to reimplement IDN decoding because keitheley return 'MODEL XXX' in the
# model field. We just want XXX
def decode_IDN(s):
    idn = _decode_IDN(s)
    idn["model"] = idn["model"].split(" ")[-1].strip()
    return idn


# arrays from keithley arrive sometimes with units (ex: A). We need to
# strip them (in the furture maybe use actual units)
def __decode_Array(s, sep=",", **kwargs):
    filt = "eE.+-," + sep
    [x for x in s if x.isdigit() or x in filt]
    return numpy.fromstring(s, sep=sep, **kwargs)


FloatArrayCmdRO = partial(Cmd, get=partial(__decode_Array, dtype=float))

# -------------------------------
# common commands to all Keithley
# -------------------------------

COMMANDS = Commands(
    _COMMANDS,
    {
        "*IDN": Cmd(get=decode_IDN, doc="identification query"),
        "REN": FuncCmd(doc="goes into remote when next addressed to listen"),
        "IFC": FuncCmd(
            doc="reset interface; all devices go into talker and listener idle states"
        ),
        "LLO": FuncCmd(doc="LOCAL key locked out"),
        "GTL": FuncCmd(doc="cancel remote; restore front panel operation"),
        "DCL": FuncCmd(doc="return all devices to known conditions"),
        "INITiate": FuncCmd(doc="trigger reading"),
        "ABORt": FuncCmd(doc="abort"),
        "READ": FloatArrayCmdRO(
            doc="trigger and return reading", func_name="read_data"
        ),
        "FETCh": FloatArrayCmdRO(
            doc="request the latest reading(s)", func_name="fetch_data"
        ),
        "CONFigure[:CURRent[:DC]]": StrCmd(
            set=None, doc="places instrument in *one-shot* measurement mode"
        ),
        "MEASure[:CURRent[:DC]]": FloatArrayCmdRO(
            doc="single measurement mode (= CONF + READ?", func_name="measure"
        ),
        "SYSTem:ZCHeck[:STATe]": OnOffCmd(doc="zero check", default=True),
        "SYSTem:ZCORrect[:STATe]": OnOffCmd(doc="zero correct", default=False),
        "SYSTem:ZCORrect:ACQuire": FuncCmd(doc="acquire a new correct value"),
        "SYSTem:PRESet": FuncCmd(doc="return system to preset defaults"),
        "SYSTem:LFRequency": IntCmd(doc="power line frequency (Hz)", default=60),
        "SYSTem:LFRequency:AUTO[:STATe]": OnOffCmd(
            doc="auto frequency detection", default=True
        ),
        "SYSTem:AZERo[:STATe]": OnOffCmd(doc="auto zero", default=True),
        "SYSTem:TIME:RESet": FuncCmd(doc="reset timestamp to 0s"),
        "SYSTem:POSetup": StrCmd(
            doc="power-on setup (RST,PRES, SAVx (x=0..2)", default="PRES"
        ),
        "SYSTem:VERSion": StrCmdRO(doc="return SCPI revision level"),
        "SYSTem:ERRor:ALL": ErrArrayCmd(doc="read and clear oldest errors"),
        "SYSTem:ERRor:COUNt": IntCmdRO(doc="return number of error messages in queue"),
        "SYSTem:ERRor:CODE[:NEXT]": IntCmdRO(doc="return and clear oldest error code"),
        "SYSTem:ERRor:CODE:ALL": IntArrayCmdRO(doc="return and clear all error codes"),
        "SYSTem:CLEar": FuncCmd(doc="clear messages from error queue"),
        "SYSTem:KEY": IntCmd(doc="get last pressed key; simulate a key-press"),
        "SYSTem:LOCal": FuncCmd(
            doc="while in LLO, removes LLO and places model in local (RS-232 only)"
        ),
        "SYSTem:REMote": FuncCmd(
            doc="places model in remote if not in LLO (RS-232 only)"
        ),
        "SYSTem:RWLock": FuncCmd(doc="places model in local lockout (RS-232 only)"),
        # status
        "STATus:MEASurement[:EVENt]": IntCmdRO(doc="read event register"),
        "STATus:MEASurement:ENABle": IntCmd(doc="program enable register"),
        "STATus:MEASurement:CONDition": IntCmdRO(doc="return condition register"),
        "STATus:OPERation:EVENT": IntCmdRO(doc="read event register"),
        "STATus:OPERation:ENABLe": IntCmd(
            doc="program event register (<NDN> or <NRf>)"
        ),
        "STATus:QUEStionable[:EVENt]": IntCmdRO(doc="read event register"),
        "STATus:QUEStionable:CONDition": IntCmdRO(doc="condition register"),
        "STATus:QUEStionable:ENABLe": IntCmd(
            doc="program event register (<NDN> or <NRf>)"
        ),
        "STATus:PRESet": FuncCmd(doc="return status registers to default values"),
        "STATus:QUEue[:NEXT]": ErrCmd(doc="return and clear oldest error code"),
        "STATus:QUEue:CLEar": FuncCmd(doc="clear messages from error queue"),
        # TODO missing STATUS:QUEUE:ENABLE,DISABLE
        # range, auto range and display
        "CURRent:RANGe[:UPPer]": FloatCmd(doc="measure current range selection"),
        "CURRent:RANGe:AUTO": OnOffCmd(doc="measure current auto range"),
        "CURRent:RANGe:AUTO:ULIMt": FloatCmd(
            doc="measure current upper range limit for auto range"
        ),
        "CURRent:RANGe:AUTO:LLIMt": FloatCmd(
            doc="measure current lower range limit for auto range"
        ),
        # buffer (TRACE == DATA subsystem)
        "TRACe:DATA": StrCmdRO(doc="read all readings in buffer"),
        "TRACe:CLEar": FuncCmd(doc="clear readings from buffer"),
        "TRACe:FREE": IntArrayCmdRO(doc="bytes available and bytes in use"),
        "TRACe:POINts": IntCmd(doc="number of reading (1..2500)", default=100),
        "TRACe:POINts:ACTual": IntCmdRO(
            doc="number of readings actually stored in buffer"
        ),
        "TRACe:FEED": StrCmd(
            doc="source of readings (SENSe1, CALCulate1 or CALCulate2)",
            default="SENSe1",
        ),
        "TRACe:FEED:CONTrol": StrCmd(
            doc="buffer control mode (NEV or NEXT)", default="NEV"
        ),
        "TRACe:TST:FORMat": StrCmd(doc="timestamp format (ABS, DELT)", default="ABS"),
        "FORMat:ELEMents": StrArrayCmd(
            doc="data elements for TRACe:DATA? response message (list of READ,UNIT,TIME,STATe)",
            default=["READ", "UNIT", "TIME", "STATe"],
        ),
        "FORMat[:DATA]": StrCmd(
            doc="data format (ASCii, REAL, 32, SREal)", default="ASC"
        ),
        "FORMat:BORDer": StrCmd(doc="byte order (NORMal, SWAPped)"),
        "FORMat:SREGister": StrCmd(
            doc="data format for status registers (ASCii, HEXadecimal, OCTal or BINary",
            default="ASC",
        ),
        # triggering
        "ARM[:SEQuence1][:LAYer1]:SOURce": StrCmd(
            doc="control source (IMM, TIMer, BUS, TLIN, MAN)", default="IMM"
        ),
        "ARM[:SEQuence1][:LAYer1]:COUNt": IntCmd(
            doc="measure count (1..2500 or INF)", default=1
        ),
        "ARM[:SEQuence1][:LAYer1]:TIMer": FloatCmd(
            doc="timer interval (s) (0.001..99999.99)", default="0.1"
        ),
        "ARM[:SEQuence1][:LAYer1][:TCONfigure]:DIRection": StrCmd(
            doc="enable (SOURce) or disable (ACC) bypass", default="ACC"
        ),
        "ARM[:SEQuence1][:LAYer1][:TCONfigure][:ASYNchronous]:ILINe": IntCmd(
            doc="input trigger line (1..6)", default=1
        ),
        "ARM[:SEQuence1][:LAYer1][:TCONfigure][:ASYNchronous]:OLINe": IntCmd(
            doc="output trigger line (1..6)", default=2
        ),
        "ARM[:SEQuence1][:LAYer1][:TCONfigure][:ASYNchronous]:OUTPut": StrCmd(
            doc="output trigger (TRIGger) or not at all (NONE)", default="NONE"
        ),
        "TRIGger:CLEar": FuncCmd(doc="clear pending input trigger immediately"),
        "TRIGger[:SEQuence1]:SOURce": StrCmd(
            doc="control source (IMM, TLIN)", default="IMM"
        ),
        "TRIGger[:SEQuence1]:COUNt": IntCmd(
            doc="measure count (1..2500 or INF)", default=1
        ),
        "TRIGger[:SEQuence1]:DELay": FloatCmd(
            doc="trigger delay (s) (0..999.9998)", default=0.
        ),
        "TRIGger[:SEQuence1]:DELay:AUTO": OnOffCmd(
            doc="enable or disable auto delay", default="OFFset"
        ),
        "TRIGger[:SEQuence1][:TCONfigure]:DIRection": Cmd(
            doc="enable (SOURce) or disable (ACC) bypass", default="ACC"
        ),
        "TRIGger[:SEQuence1][:TCONfigure][:ASYNchronous]:ILINe": IntCmd(
            doc="input trigger line (1..6)", default=1
        ),
        "TRIGger[:SEQuence1][:TCONfigure][:ASYNchronous]:OLINe": IntCmd(
            doc="output trigger line (1..6)", default=2
        ),
        "TRIGger[:SEQuence1][:TCONfigure][:ASYNchronous]:OUTPut": StrCmd(
            doc="output trigger after measurement (SENS) or not at all (NONE)",
            default="NONE",
        ),
        # display
    },
)

# --------------------------------
# Keithley model specific commands
# --------------------------------

# math subsystem: mX+b, m/X+b and log (CALCulate1)
_mXb_commands = {
    "FORMat": StrCmd(doc="select calculation: MXB, REC or LOG10", default="MXB"),
    "KMATh:MMFactor": FloatCmd(doc="scale factor (M) for mX+b and m/X+b", default=1.0),
    "KMATh:MBFactor": FloatCmd(doc="scale factor (B) for mX+b and m/X+b", default=0.0),
    "KMATh:MUNits": FloatCmd(
        doc="units for mX+b and m/X+b (A-Z,'[' for ohm, '' for degree, ] for % ",
        default="X",
    ),
    "STATe": OnOffCmd(doc="enable/disable selected calculation", default=False),
    "DATA": StrCmdRO(doc="return all CALC1 results triggered by INIT"),
    "DATA:LATest": StrCmdRO(doc="return last reading"),
}

# relative offset
_offset_commands = {
    "FEED": StrCmd(doc="reading to Rel (SENSe[1], CALCulate[1])", default="SENSe1"),
    "NULL:ACQuire": FuncCmd(doc="use input signal as Rel value"),
    "NULL:OFFSet": FloatCmd(doc="rel value", default=0.0),
    "NULL[:STATe]": OnOffCmd(doc="Rel enable", default=False),
    "DATA": IntCmdRO(doc="return Rel'ed readings triggered by INITIATE"),
    "DATA:LATest": StrCmd(doc="return only the latest Rel'ed reading"),
}

# limits
_limits_commands = {
    # limit tests
    "LIMit1:UPPer[:DATA]": FloatCmd(
        doc="upper limit 1 (-9.99999e20..9.99999e20)", default=1.
    ),
    "LIMit1:LOWer[:DATA]": FloatCmd(
        doc="lower limit 1 (-9.99999e20..9.99999e20)", default=-1.
    ),
    "LIMit1:STATe": OnOffCmd(doc="enable/disable limit 1 test", default=False),
    "LIMit1:FAIL": IntCmdRO(doc="result of limit 1 test (False: pass, True: fail)"),
    "LIMit2:UPPer[:DATA]": FloatCmd(
        doc="upper limit 2 (-9.99999e20..9.99999e20)", default=1.
    ),
    "LIMit2:LOWer[:DATA]": FloatCmd(
        doc="lower limit 2 (-9.99999e20..9.99999e20)", default=-1.
    ),
    "LIMit2:STATe": OnOffCmd(doc="enable/disable limit 2 test", default=False),
    "LIMit2:FAIL": IntCmdRO(doc="result of limit 2 test (False: pass, True: fail)"),
    "NULL:OFFset": FloatCmd(doc="Rel value (-9.99999e20..9.99999e20)", default=0.),
    "NULL[:STATe]": OnOffCmd(doc="enable/disable Rel", default=False),
}

_buffer_config_commands = {
    "FORMat": StrCmd(
        doc="buffer statistic (MINimum,MAXimum,MEAN,SDEViation,PKPK", default="MEAN"
    ),
    "DATA": FloatCmdRO(doc="read the selected buffer statistic"),
}

_ratio_commands = {
    "FORMat": StrCmd(
        doc="ratio math (C3C4=CALC3/CALC4 or C4C3=CALC4/CALC3)", default="C3C4"
    ),
    "STATe": OnOffCmd(doc="enable/disable ratio math", default=False),
    "DATA": FloatArrayCmdRO(doc="request data"),
}

_display_commands = {
    "DISPlay:DIGits": IntCmd(doc="display resolution (4..7)", default=6),
    "DISPlay:ENABle": OnOffCmd(doc="front panel display on/off"),
    "DISPlay{window}:TEXT:DATA": StrCmd(doc="ascii message (max 12 chars)"),
    "DISPlay{window}:TEXT:STATe": OnOffCmd(doc="text message status"),
}

_sens_commands = {
    # SENSe1
    "FUNCtion": StrCmd(doc="measure function (CURRent:DC)", default="CURRent"),
    "DATA[:LATest]": StrCmdRO(doc="return last instrument reading"),
    # median filter
    "MEDian[:STATe]": OnOffCmd(doc="median filter enable", default=False),
    "MEDian:RANK": IntCmd(doc="median filter rank (1-5)", default=1),
    # digital filter
    "AVERage[:STATe]": OnOffCmd(doc="digital filter enable", default=False),
    "AVERage:TCONtrol": StrCmd(doc="filter control (MOV, REP)", default="REP"),
    "AVERage:COUNt": IntCmd(doc="filter count (2-100)", default=10),
    "AVERage:ADVanced[:STATe]": OnOffCmd(
        doc="advanced digital filter enable", default=False
    ),
    "AVERage:ADVanced:NTOLerance": IntCmd(doc="noise tolerance (%) (0-105)", default=0),
}

_sens_curr_commands = {
    # SENSe1
    "CURRent[:DC]:NPLCycles": FloatCmd(
        doc="integration rate in line cycles (PLCs) (0.01..5/6)"
    ),
    "CURRent[:DC]:RANGe[:UPPer]": FloatCmd(doc="select range (A) (-0.021..0.021)"),
    "CURRent[:DC]:RANGe:AUTO": OnOffCmd(doc="enable/disable auto-range"),
    "CURRent[:DC]:RANGe[:AUTO]:ULIM": FloatCmd(
        doc="auto-range upper limit (A) (-0.021..0.021)"
    ),
    "CURRent[:DC]:RANGe[:AUTO]:LLIM": FloatCmd(
        doc="auto-range lower limit (A) (-0.021..0.021)"
    ),
}

_sens_volt_commands = {
    # SENSe1
    "VOLTage[:DC]:NPLCycles": FloatCmd(
        doc="integration rate in line cycles (PLCs) (0.01..5/6)"
    ),
    "VOLTage[:DC]:RANGe[:UPPer]": FloatCmd(doc="select range (V) (-210..210)"),
    "VOLTage[:DC]:RANGe:AUTO": OnOffCmd(doc="enable/disable auto-range"),
    "VOLTage[:DC]:RANGe[:AUTO]:ULIM": FloatCmd(
        doc="auto-range upper limit (V) (-210..210)"
    ),
    "VOLTage[:DC]:RANGe[:AUTO]:LLIM": FloatCmd(
        doc="auto-range lower limit (V) (-210..210)"
    ),
    "VOLTage[:DC]:GUARd": OnOffCmd(doc="enable/disable driven guard"),
    "VOLTage[:DC]:XFEedback": OnOffCmd(doc="enable/disable external feedback"),
}

_sens_res_commands = {
    # SENSe1
    "RESistance:NPLCycles": FloatCmd(
        doc="integration rate in line cycles (PLCs) (0.01..5/6)"
    ),
    "RESistance:RANGe[:UPPer]": FloatCmd(doc="select range (ohms) (0..2.1e-11)"),
    "RESistance:RANGe:AUTO": OnOffCmd(doc="enable/disable auto-range"),
    "RESistance:RANGe[:AUTO]:ULIM": FloatCmd(
        doc="auto-range upper limit (ohms) (0..2.1e-11)"
    ),
    "RESistance:RANGe[:AUTO]:LLIM": FloatCmd(
        doc="auto-range lower limit (ohms) (0..2.1e-11)"
    ),
    "RESistance:GUARd": OnOffCmd(doc="enable/disable driven guard"),
}

_sens_char_commands = {
    # SENSe1
    "CHARge:NPLCycles": FloatCmd(
        doc="integration rate in line cycles (PLCs) (0.01..5/6)"
    ),
    "CHARge:RANGe[:UPPer]": FloatCmd(doc="select range (coulombs) (-21e-6..21e-6)"),
    "CHARge:RANGe:AUTO": OnOffCmd(doc="enable/disable auto-range"),
    "CHARge:RANGe[:AUTO]:LGRoup": StrCmd(doc="auto-range limit (HIGH, LOW)"),
    "CHARge:ADIScharge:LEVel": FloatCmd(doc="set auto-discharge level (-21e-6..21e-6)"),
    "CHARge:ADIScharge:STATe": OnOffCmd(doc="enable/disable auto-discharge"),
}


def __get_commands(cmds, subsystem):
    r = {}
    for k, v in cmds.items():
        k = "{0}{1}".format(subsystem, k)
        r[k] = v
    return r


def __get_display_commands(window="[:WINDow1]"):
    r = {}
    for k, v in _display_commands.items():
        k = k.format(window=window)
        r[k] = v
    return r


__get_mXb_commands = partial(__get_commands, _mXb_commands)
__get_offset_commands = partial(__get_commands, _offset_commands)
__get_limits_commands = partial(__get_commands, _limits_commands)
__get_buffer_config_commands = partial(__get_commands, _buffer_config_commands)
__get_ratio_commands = partial(__get_commands, _ratio_commands)
__get_sens_commands = partial(__get_commands, _sens_commands)
__get_sens_curr_commands = partial(__get_commands, _sens_curr_commands)
__get_sens_volt_commands = partial(__get_commands, _sens_volt_commands)
__get_sens_res_commands = partial(__get_commands, _sens_res_commands)
__get_sens_char_commands = partial(__get_commands, _sens_char_commands)

_6482_commands = Commands()
_6482_commands.update(__get_mXb_commands("CALCulate[1]:"))
_6482_commands.update(__get_mXb_commands("CALCulate2:"))
_6482_commands.update(__get_offset_commands("CALCulate3:"))
_6482_commands.update(__get_offset_commands("CALCulate4:"))
_6482_commands.update(__get_ratio_commands("CALCulate5:"))
_6482_commands.update(__get_ratio_commands("CALCulate6:"))
_6482_commands.update(
    __get_limits_commands("CALCulate7:")
)  # TODO missing LIMitX, CLIMITs
_6482_commands.update(__get_buffer_config_commands("CALCulate8:"))
_6482_commands.update(__get_display_commands("[:WINDow1]"))
_6482_commands.update(__get_display_commands("[:WINDow2]"))
_6482_commands.update(__get_sens_commands("[SENSe[1]:]"))
_6482_commands.update(__get_sens_curr_commands("[SENSe[1]:]"))
_6482_commands.update(__get_sens_commands("SENSe2:"))
_6482_commands.update(__get_sens_curr_commands("SENSe2:"))

_6485_commands = Commands()
_6485_commands.update(__get_mXb_commands("CALCulate[1]:"))
_6485_commands.update(__get_offset_commands("CALCulate2:"))
_6485_commands.update(__get_limits_commands("CALCulate2:"))
_6485_commands.update(__get_buffer_config_commands("CALCulate3:"))
_6485_commands.update(__get_display_commands("[:WINDow1]"))
_6485_commands.update(__get_sens_commands("[SENSe[1]:]"))
_6485_commands.update(__get_sens_curr_commands("[SENSe[1]:]"))

_6514_commands = Commands()
_6514_commands.update(__get_mXb_commands("CALCulate[1]:"))
_6514_commands.update(__get_offset_commands("CALCulate2:"))
_6514_commands.update(__get_limits_commands("CALCulate2:"))
_6514_commands.update(__get_buffer_config_commands("CALCulate3:"))
_6514_commands.update(__get_display_commands("[:WINDow1]"))
_6514_commands.update(__get_sens_commands("[SENSe[1]:]"))
_6514_commands.update(__get_sens_curr_commands("[SENSe[1]:]"))
_6514_commands.update(__get_sens_volt_commands("[SENSe[1]:]"))
_6514_commands.update(__get_sens_res_commands("[SENSe[1]:]"))
_6514_commands.update(__get_sens_char_commands("[SENSe[1]:]"))

import collections

MODEL_COMMANDS = collections.defaultdict(Commands)
MODEL_COMMANDS.update(
    {"6482": _6482_commands, "6485": _6485_commands, "6514": _6514_commands}
)
