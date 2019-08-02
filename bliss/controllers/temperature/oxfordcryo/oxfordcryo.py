# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Oxford Cryosystems 700 Series
    cryo_700_series_manual.pdf, pages 38-39:
    (http://www.oxcryo.com/serialcomms/700series/cs_status.html)

     Status Packets
     ---------------
     Cryostream issues 'status packets' at regular (1 second) intervals.
     This does not require any 'status request' command.
     The status packets are of a fixed length and format detailed below:

     typedef struct {
        unsigned char Length; /* Length of this packet = 32 (bytes) */
        unsigned char Type; /* Status Packet ID = 1 */
        unsigned short GasSetPoint; /* Set Temp 100*K */
        unsigned short GasTemp; /* Gas Temp 100*K */
        signed short GasError; /* Error 100*K */
        unsigned char RunMode; /* The current 'run mode' */
        unsigned char PhaseId; /* theState.PhaseTable[0].Id */
        unsigned short RampRate; /* theState.PhaseTable[0].Temp */
        unsigned short TargetTemp; /* theState.PhaseTable[0].Temp */
        unsigned short EvapTemp; /* Evap temp, 100*K */
        unsigned short SuctTemp; /* Suct temp, 100*K */
        unsigned short Remaining; /* Time remaining in phase */
        unsigned char GasFlow; /* Gas flow, 10*l/min */
        unsigned char GasHeat; /* Gas heater, % */
        unsigned char EvapHeat; /* Evap heater, % */
        unsigned char SuctHeat; /* Suct heater, % */
        unsigned char LinePressure; /* Back pressure, 100*bar */
        unsigned char AlarmCode; /* Indicates most serious alarm condition */
        unsigned short RunTime; /* Time in minutes pump has been up */
        unsigned short ControllerNumber; /* Controller number, from ROM */
        unsigned char SoftwareVersion; /* Software version */
        unsigned char EvapAdjust; /* EvapAdjust vacuum compensation */
     } CryostreamStatus ;

     Notes
      * chars have a size of 1 byte, shorts have a size of 2 bytes.
      * All temperatures are in centi-Kelvin, i.e. 80 K is reported as 8000.
      * The RunMode member make take the following values:

     enum {
        StartUp, /* = 0: Initial transient value - run through system checks */
        StartUpFail, /* = 1: Some failure in system checks - leave results on
        screen */
        StartUpOK, /* = 2: System checks OK - awaiting Start button */
        Run, /* = 3: Gas is flowing */
        SetUp, /* = 4: Special commissioning mode */
        ShutdownOK, /* = 5: System has shut down cleanly */
        ShutdownFail /* = 6: System has shut down due to hardware error */
     };

     The PhaseId member may take the following values, whose meaning
     should be obvious from the manual. This parameter is meaningless
     unless iRunMode = Run.  Parameters of the current phase are
     stored in the RampRate, TargetTemp and Remaining members.

     enum {
        Ramp, /* = 0: Current phase is a Ramp */
        Cool, /* = 1: Current phase is a Cool */
        Plat, /* = 2: Current phase is a Plat */
        Hold, /* = 3: Current phase is a Hold */
        End, /* = 4: Current phase is an End */
        Purge, /* = 5: Current phase is a Purge */
        DeletePhase, /* = 6: Internal use only */
        LoadProgram, /* = 7: Internal use only */
        SaveProgram, /* = 8: Internal use only */
        Soak, /* = 9: Part of the Purge phase */
        Wait /* = 10: Part of Ramp/Wait */
     };

     The AlarmCode member make take the following values.

     enum {
        AlarmConditionNone, /* = 0: No alarms exist */
        AlarmConditionStopPressed, /* = 1: Stop button has been pressed */
        AlarmConditionStopCommand, /* = 2: Stop command received */
        AlarmConditionEnd, /* = 3: End phase complete */
        AlarmConditionPurge, /* = 4: Purge phase complete */
        AlarmConditionTempWarning, /* = 5: Temp error > 5 K */
        AlarmConditionHighPressure, /* = 6: Back pressure > 0.5 bar */
        AlarmConditionVacuum, /* = 7: Evaporator reduction at max */
        AlarmConditionStartUpFail, /* = 8: Self-check fail */
        AlarmConditionLowFlow, /* = 9: Gas flow < 2 l/min */
        AlarmConditionTempFail, /* = 10: Temp error > 25 K */
        AlarmConditionTempReadingError,/* = 11: Unphysical temp. reported */
        AlarmConditionSensorFail, /* = 12: Invalid ADC reading */
        AlarmConditionBrownOut, /* = 13: Degradation of power supply */
        AlarmConditionHeatsinkOverheat,/* = 14: Heat sink overheating */
        AlarmConditionPsuOverheat, /* = 15: Power supply overheating */
        AlarmConditionPowerLoss /* = 16: Power failure */
     };

"""

import time
import datetime


class StatusPacket(object):
    """
    bytes 0 to 31
    L T GS 2GT 2GE R P 2RR 2TT 2ET 2ST 2R GF GH EH SH LP AC 2RT 2CN SV EA
    """

    Length_c_idx = 0
    Type_c_idx = 1
    GasSetPoint_s_idx = 2
    GasTemp_s_idx = 4
    GasError_s_idx = 6
    RunMode_c_idx = 8
    PhaseId_c_idx = 9
    RampRate_s_idx = 10
    TargetTemp_s_idx = 12
    EvapTemp_s_idx = 14
    SuctTemp_s_idx = 16
    Remaining_s_idx = 18
    GasFlow_c_idx = 20
    GasHeat_c_idx = 21
    EvapHeat_c_idx = 22
    SuctHeat_c_idx = 23
    LinePressure_c_idx = 24
    AlarmCode_c_idx = 25
    RunTime_s_idx = 26
    ControllerNumber_s_idx = 28
    SoftwareVersion_c_idx = 30
    EvapAdjust_c_idx = 31

    RUNMODE_CODES = [
        "StartUp",
        "StartUpFail",
        "StartUpOK",
        "Run",
        "SetUp",
        "ShutdownOK",
        "ShutdownFail",
    ]

    PHASE_CODES = [
        "Ramp",
        "Cool",
        "Plat",
        "Hold",
        "End",
        "Purge",
        "DeletePhase",
        "LoadProgram",
        "SaveProgram",
        "Soak",
        "Wait",
    ]

    ALARM_CODES = [
        "AlarmConditionNone",
        "AlarmConditionStopPressed",
        "AlarmConditionStopCommand",
        "AlarmConditionEnd",
        "AlarmConditionPurge",
        "AlarmConditionTempWarning",
        "AlarmConditionHighPressure",
        "AlarmConditionVacuum",
        "AlarmConditionStartUpFail",
        "AlarmConditionLowFlow",
        "AlarmConditionTempFail",
        "AlarmConditionTempReadingError",
        "AlarmConditionSensorFail",
        "AlarmConditionBrownOut",
        "AlarmConditionHeatsinkOverheat",
        "AlarmConditionPsuOverheat",
        "AlarmConditionPowerLoss",
    ]

    def __init__(self, data, timestamp=None):
        self.timestamp = timestamp or time.time()
        self.length = data[self.Length_c_idx]
        self.type = data[self.Type_c_idx]
        self.gas_set_point = (
            self.get_short(data[self.GasSetPoint_s_idx : self.GasSetPoint_s_idx + 2])
            / 100.0
        )
        self.gas_temp = (
            self.get_short(data[self.GasTemp_s_idx : self.GasTemp_s_idx + 2]) / 100.0
        )
        self.gas_error = (
            self.get_signed_short(data[self.GasError_s_idx : self.GasError_s_idx + 2])
            / 100.0
        )
        self.run_mode_code = data[self.RunMode_c_idx]
        self.run_mode = self.RUNMODE_CODES[self.run_mode_code]
        self.phase_code = data[self.PhaseId_c_idx]
        self.phase = self.PHASE_CODES[self.phase_code]
        self.ramp_rate = self.get_short(
            data[self.RampRate_s_idx : self.RampRate_s_idx + 2]
        )
        self.target_temp = (
            self.get_short(data[self.TargetTemp_s_idx : self.TargetTemp_s_idx + 2])
            / 100.0
        )
        self.evap_temp = (
            self.get_short(data[self.EvapTemp_s_idx : self.EvapTemp_s_idx + 2]) / 100.0
        )
        self.suct_temp = (
            self.get_short(data[self.SuctTemp_s_idx : self.SuctTemp_s_idx + 2]) / 100.0
        )
        self.remaining = self.get_short(
            data[self.Remaining_s_idx : self.Remaining_s_idx + 2]
        )
        self.gas_flow = data[self.GasFlow_c_idx] / 10.0
        self.gas_heat = data[self.GasHeat_c_idx]
        self.evap_heat = data[self.EvapHeat_c_idx]
        self.suct_heat = data[self.SuctHeat_c_idx]
        self.line_pressure = data[self.LinePressure_c_idx]
        self.alarm_code = data[self.AlarmCode_c_idx]
        self.alarm = self.ALARM_CODES[self.alarm_code]
        self.run_time = self.get_short(
            data[self.RunTime_s_idx : self.RunTime_s_idx + 2]
        )
        self.run_days = self.run_time / (60 * 24)
        self.run_hours = (self.run_time - (self.run_days * 24 * 60)) / 60
        self.run_mins = (
            self.run_time - (self.run_days * 24 * 60) - (self.run_hours * 60)
        )
        self.controller_nb = self.get_short(
            data[self.ControllerNumber_s_idx : self.ControllerNumber_s_idx + 2]
        )
        self.software_version = data[self.SoftwareVersion_c_idx]
        self.evap_adjust = data[self.EvapAdjust_c_idx]

    def get_short(self, data):
        """Construct short from two bytes
           Args:
             (list): data from the controller
           Returns:
              (short): the constructed short value
        """
        return (data[0] << 8) + data[1]

    def get_signed_short(self, data):
        """Construct signed short from two bytes
           Args:
             (list): data from the controller
           Returns:
              (short): the constructed short value
        """
        # reverting two's complement if necessary
        short = self.get_short(data)
        # checking if value is negative
        if (short & 0b1000000000000000) >> 15:
            short = ~short
            short += 1
            short &= 0b1111111111111111
            short *= -1  # returning the negative value
        return short

    def __info__(self):
        timestamp = datetime.datetime.fromtimestamp(self.timestamp)
        pretty_print = "Status Packet:"
        pretty_print += "\nReading made at %s" % str(timestamp)
        pretty_print += "\nlength: %d" % self.length
        pretty_print += "\ntype: %d" % self.type
        pretty_print += "\ngas set point: %.2f (K)" % self.gas_set_point
        pretty_print += "\ngas temp: %.2f (K)" % self.gas_temp
        pretty_print += "\ngas error: %.2f (K)" % self.gas_error
        pretty_print += "\nrun mode code: %d" % self.run_mode_code
        pretty_print += "\nrun mode: %s" % self.run_mode
        pretty_print += "\nphase code: %d" % self.phase_code
        pretty_print += "\nphase: %s" % self.phase
        pretty_print += "\nramp rate: %d (K/h)" % self.ramp_rate
        pretty_print += "\ntarget temp: %.2f (K)" % self.target_temp
        pretty_print += "\nevap temp: %.2f (K)" % self.evap_temp
        pretty_print += "\nsuct temp: %.2f (K)" % self.suct_temp
        pretty_print += "\nremaining: %d" % self.remaining
        pretty_print += "\ngas flow: %f (l/min)" % self.gas_flow
        pretty_print += "\ngas heat: %d %%" % self.gas_heat
        pretty_print += "\nevap heat: %d %%" % self.evap_heat
        pretty_print += "\nsuct heat: %d %%" % self.suct_heat
        pretty_print += "\nline pressure: %d (100*bar)" % self.line_pressure
        pretty_print += "\nalarm code: %d" % self.alarm_code
        pretty_print += "\nalarm: %s" % self.alarm
        pretty_print += "\nrun time: %d (min): %dd %dh %dm" % (
            self.run_time,
            self.run_days,
            self.run_hours,
            self.run_mins,
        )
        pretty_print += "\ncontroller number: %d" % self.controller_nb
        pretty_print += "\nsoftware version: %d" % self.software_version
        pretty_print += "\nevap adjust: %d" % self.evap_adjust
        return pretty_print


class Struct(object):
    """Make an enum"""

    def __init__(self, **entries):
        self.__dict__.update(entries)


Enum = Struct
CSCOMMAND = Enum(
    RESTART=10,
    RAMP=11,
    PLAT=12,
    HOLD=13,
    COOL=14,
    END=15,
    PURGE=16,
    PAUSE=17,
    RESUME=18,
    STOP=19,
    TURBO=20,
)


def split_bytes(number):
    """splits high and low byte (two less significant bytes)
       of an integer, and returns them as chars
    """
    if not isinstance(number, int):
        raise Exception("split_bytes: Wrong imput - should be an integer.")
    low = number & 0b11111111
    high = (number >> 8) & 0b11111111
    return bytes([high]), bytes([low])
