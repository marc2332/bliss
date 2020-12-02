# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import datetime
import enum
import weakref
import gevent

from bliss.comm.util import get_comm
from bliss import global_map

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


class StatusPacket:
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
        "DeletePhase",  # different from doc ?
        "LoadProgram",  # different from doc ?
        "SaveProgram",  # different from doc ?
        "Soak",  # different from doc ?
        "Wait",  # different from doc ?
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


class CSCOMMAND(enum.IntEnum):
    RESTART = 10
    RAMP = 11
    PLAT = 12
    HOLD = 13
    COOL = 14
    END = 15
    PURGE = 16
    PAUSE = 17
    RESUME = 18
    STOP = 19
    TURBO = 20


class CSCMDSIZE(enum.IntEnum):
    RESTART = 2
    RAMP = 6
    PLAT = 4
    HOLD = 2
    COOL = 4
    END = 2
    PURGE = 2
    PAUSE = 2
    RESUME = 2
    STOP = 2
    TURBO = 3


def split_bytes(number):
    """splits high and low byte (two less significant bytes)
       of an integer, and returns them as chars
    """
    if not isinstance(number, int):
        raise Exception("split_bytes: Wrong imput - should be an integer.")
    low = number & 0b11111111
    high = (number >> 8) & 0b11111111
    return bytes([high]), bytes([low])


class OxfordCryostream:
    """
    OXCRYO_ALARM = {0:"No Alarms",
                 1:"Stop button has been pressed",
                 2:"Stop command received",
                 3:"End phase complete",
                 4:"Purge phase complete",
                 5:"Temperature error > 5 K",
                 6:"Back pressure > 0.5 bar",
                 7:"Evaporator reduction at maximum",
                 8:"Self-check failed",
                 9:"Gas flow < 2 l/min",
                 10:"Temperature error >25 K",
                 11:"Sensor detects wrong gas type",
                 12:"Unphysical temperature reported",
                 13:"Suct temperature out of range",
                 14:"Invalid ADC reading",
                 15:"Degradation of power supply",
                 16:"Heat sink overheating",
                 17:"Power supply overheating",
                 18:"Power failure",
                 19:"Refrigerator stage too cold",
                 20:"Refrigerator stage failed to reach base in time",
                 21:"Cryodrive is not responding ",
                 22:"Cryodrive reports an error ",
                 23:"No nitrogen available ",
                 24:"No helium available ",
                 25:"Vacuum gauge is not responding ",
                 26:"Vacuum is out of range ",
                 27:"RS232 communication error ",
                 28:"Coldhead temp > 315 K ",
                 29:"Coldhead temp > 325 K ",
                 30:"Wait for End to complete ",
                 31:"Do not open the cryostat ",
                 32:"Disconnect Xtal sensor ",
                 33:"Cryostat is open ",
                 34:"Cryostat open for more than 10 min ",
                 35:"Sample temp > 320 K ",
                 36:"Sample temp > 325 K"}
    """

    def __init__(self, cfg):
        """RS232 settings: 9600 baud, 8 bits, no parity, 1 stop bit
        """

        # port = cfg["serial"]["url"]
        self.serial = get_comm(cfg)  # Serial(port, baudrate=9600, eol="\r")
        global_map.register(self.serial, parents_list=[self, "comms"])
        # global_map.register(
        #     self,
        #     parents_list=["comms"],
        #     children_list=[self.serial],
        #     tag=f"oxford700: {port}",
        # )
        self._status_packet = None
        self._update_task = gevent.spawn(self._update_status, weakref.proxy(self))
        self._event = gevent.event.Event()

    # ? or del ?
    def __exit__(self, etype, evalue, etb):
        self.serial.close()

    def restart(self):
        """Restart a Cryostream which has shutdown
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.RESTART.value, CSCOMMAND.RESTART.value)

    def purge(self):
        """Warm up the Coldhead as quickly as possible
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.PURGE.value, CSCOMMAND.PURGE.value)

    def stop(self):
        """Immediately halt the Cryostream Cooler,turning off the pump and
           all the heaters - used for emergency only

           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.STOP.value, CSCOMMAND.STOP.value)

    def hold(self):
        """Maintain temperature fixed indefinitely, until start issued.
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.HOLD.value, CSCOMMAND.HOLD.value)

    def pause(self):
        """Start temporary hold
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.PAUSE.value, CSCOMMAND.PAUSE.value)

    def resume(self):
        """Exit temporary hold
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.RESUME.value, CSCOMMAND.RESUME.value)

    def turbo(self, flow):
        """Switch on/off the turbo gas flow
           Args:
              flow (bool): True when turbo is on (gas flow 10 l/min)
           Returns:
              None
        """
        self.send_cmd(CSCMDSIZE.TURBO.value, CSCOMMAND.TURBO.value, int(flow))

    def cool(self, temp=None):
        """Make gas temperature decrease to a set value as quickly as possible
           Args:
              temp (float): final temperature [K]
           Returns:
              (float): current gas temperature setpoint
        """
        if temp:
            temp = int(temp * 100)
            self.send_cmd(CSCMDSIZE.COOL.value, CSCOMMAND.COOL.value, temp)
        else:
            return self.statusPacket.gas_set_point

    def plat(self, duration=None):
        """Maintain temperature fixed for a certain time.
           Args:
              duration (int): time [minutes]
           Returns:
              (int): remaining time [minutes]
        """
        try:
            self.send_cmd(CSCMDSIZE.PLAT.value, CSCOMMAND.PLAT.value, int(duration))
        except (TypeError, ValueError):
            return self.statusPacket.remaining

    def end(self, rate):
        """System shutdown with Ramp Rate to go back to temperature of 300K
           Args:
              rate (int): ramp rate [K/hour]
        """
        try:
            self.send_cmd(CSCMDSIZE.END.value, CSCOMMAND.END.value, int(rate))
        except (TypeError, ValueError):
            pass

    def ramp(self, rate=None, temp=None):
        """Change gas temperature to a set value at a controlled rate
           Args:
              rate (int): ramp rate [K/hour], values 1 to 360
              temp (float): target temperature [K]
           Returns:
              (float, float): current ramp rate [K/hour],
                              target temperature [K]
        """
        if rate == None:
            rate = self.statusPacket.ramp_rate
        if rate == 0:
            print("Oxford700: ramprate is 0! Please set ramprate first!")
            return
        if temp == None:
            temp = self.statusPacket.target_temp
        if temp == 0.0:
            temp = self.statusPacket.gas_temp

        # try:
        temp = int(temp * 100)  # transfering to centi-Kelvin
        self.send_cmd(CSCMDSIZE.RAMP.value, CSCOMMAND.RAMP.value, int(rate), temp)
        # except (TypeError, ValueError):
        #    raise

    def is_ramping(self):
        return self.statusPacket.phase in ["Ramp", "Wait"]

    def is_paused(self):
        return self.statusPacket.phase == "Hold"

    def read_sample_setpoint(self):
        """ Read sample setpoint.
            Return a value in Kelvin.
        """
        return self.statusPacket.gas_set_point

    def read_sample_temperature(self):
        """ Read sample temperature.
            Return a value in Kelvin
        """
        return self.statusPacket.gas_temp

    def read_sample_error(self):
        """ Read sample error.
            Return a value in Kelvin.
        """
        return self.statusPacket.gas_error

    def read_run_mode(self):
        """ Read the current run mode (str) """
        return self.statusPacket.run_mode

    def read_phase(self):
        """ Read the current phase (str) """
        return self.statusPacket.phase

    def read_ramprate(self):
        """ Read the ramprate of current phase.
            Return a value in Kelvin/hour.
        """
        return self.statusPacket.ramp_rate

    def read_target_temperature(self):
        """ Read the target temperature of the current phase.
            Return a value in Kelvin.
        """
        return self.statusPacket.target_temp

    def read_shield_temperature(self):
        """ Read the shield temperature
            Return a value in Kelvin.
        """
        return self.statusPacket.evap_temp

    def read_cold_head_temperature(self):
        """ Read the cold head temperature
            Return a value in Kelvin.
        """
        return self.statusPacket.suct_temp

    def read_gas_flow(self):
        """ Read the gas flow (cryodrive speed).
        """
        return self.statusPacket.gas_flow

    def read_sample_heat(self):
        """ Read the sample stage heater.
        """
        return self.statusPacket.gas_heat

    def read_shield_heat(self):
        """ Read the shield heater.
        """
        return self.statusPacket.evap_heat

    def read_average_sample_heat(self):
        """ Read the average value of sample heater.
        """
        return self.statusPacket.suct_heat

    def read_cryodrive_status(self):
        """ Read cryodrive status.
        """
        return self.statusPacket.line_pressure

    def read_alarm(self):
        """ Read the alarm. Indicates most serious alarm condition
        """
        return self.statusPacket.alarm

    def send_cmd(self, size, command, *args):
        """Create a command packet and write it to the controller
           Args:
              size (int): The variable size of the command packet
              command (int): The command packet identifier (command name)
              args: Possible variable number of parameters
           Returns:
              None
        """
        self._event.clear()
        self._event.wait()
        data = [bytes([size]), bytes([command])]
        if size == 3:
            data.append(str(args[0]).encode())
        elif size > 3:
            hbyte, lbyte = split_bytes(args[0])
            data.append(hbyte)
            data.append(lbyte)
            try:
                hbyte, lbyte = split_bytes(args[1])
                data.append(hbyte)
                data.append(lbyte)
            except Exception as e:
                print(e)

        data_str = b"".join(data)
        # print([ d.hex() for d in data ])
        # print(data_str.hex())
        self.serial.write(data_str)

    @property
    def statusPacket(self):
        status = self._status_packet
        # synchronize first read
        with gevent.Timeout(10):
            while status is None:
                gevent.sleep(0.1)
                status = self._status_packet
        if isinstance(status, Exception):
            raise status
        return status

    @staticmethod
    def _update_status(ctrl_proxy):
        try:
            while True:
                try:
                    status = ctrl_proxy._update_cmd()
                except Exception as error:
                    status = error
                else:
                    ctrl_proxy._event.set()  # command synchronization
                ctrl_proxy._status_packet = status
        except ReferenceError:
            pass

    def _update_cmd(self):
        """Read the controller and update all the parameter variables
           Args:
              None
           Returns:
              None
        """
        # read the data
        data = self.serial._read(32, 10)

        # check if data
        if not data:
            raise RuntimeError("Invalid answer from Cryostream")

        if len(data) != 32:
            data = self.serial._read(32, 10)
        data = [nb for nb in data]
        if data[0] == 32:
            return StatusPacket(data)
