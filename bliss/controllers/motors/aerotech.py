# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.comm.util import TCP,get_comm
from bliss.comm.tcp import SocketTimeout
from bliss.common.axis import AxisState
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller

import string
import time
import gevent
from collections import namedtuple


class AerotechStatus(object):
    def __init__(self, value, bitdef):
        self._bitdef = bitdef
        self._valdict = dict([(name, False) for name,bitidx in self._bitdef])
        self.set(value)

    def set(self, value):
        self._value= value
        for name,bitidx in self._bitdef:
            self._valdict[name]= bool(value & (1<<bitidx))

    def get(self):
        return self._value

    def __str__(self):
        stastr= ""
        for name, bitidx in self._bitdef:
            stastr += " * %20.20s = %s\n"%(name, self._valdict[name])
        return stastr

    def __getattr__(self, name):
        value = self._valdict.get(name, None)
        if value is None:
            raise ValueError("Unknown field : %s"%name)
        return value

class AerotechAxis(object):
    def __init__(self, name, axis, speed):
        self.name = name
        self.axis = axis
        self.speed = speed

class Aerotech(Controller):
    """
    Aerotech motor controller

    configuration example:
    - class: aerotech
      tcp:
        url: id15aero1
      axes:
        - name: rot
          aero_name: X
          steps_per_unit: 26222.2
          velocity: 377600
          acceleration: 755200

    default port 8000 if not specified
    """

    CMD_TERM = '\n'
    RET_SUCCESS = '%'
    RET_INVALID = '!'
    RET_FAULT = '#'
    RET_TIMEOUT = '$'

    AXIS_STATUS_BITS= (("Enabled", 0),
                       ("Homed", 1),
                       ("InPosition", 2),
                       ("MoveActive", 3),
                       ("AccelPhase", 4),
                       ("DecelPhase", 5),
                       ("PositionCapture", 6),
                       ("CurrentClamp", 7),
                       ("BrakeOutput", 8),
                       ("MotionDirection", 9),
                       ("MasterSlaveControl", 10),
                       ("CalActive", 11),
                       ("CalEnabled", 12),
                       ("JoystickControl", 13),
                       ("Homing", 14),
                       ("MasterSuppress", 15),
                       ("GantryActive", 16),
                       ("GantryMaster", 17),
                       ("AutofocusActive", 18),
                       ("CommandFilterDone", 19),
                       ("InPosition2", 20),
                       ("ServoControl", 21),
                       ("PositiveLimit", 22),
                       ("NegativeLimit", 23),
                       ("HomeLimit", 24),
                       ("MarkerInput", 25),
                       ("HallAInput", 26),
                       ("HallBInput", 27),
                       ("HallCInput", 28),
                       ("SineEncoderError", 29),
                       ("CosineEncoderError", 30),
                       ("EmergencyStop", 31)
                      )

    AXIS_FAULT_BITS= (("PositionError", 0),
                      ("OverCurrent", 1),
                      ("PositiveHardLimit", 2),
                      ("NegativeHardLimit", 3),
                      ("PositiveSoftLimit", 4),
                      ("NegativeSoftLimit", 5),
                      ("AmplifierFault", 6),
                      ("PositionFbk", 7),
                      ("VelocityFbk", 8),
                      ("HallSensor", 9),
                      ("MaxVelocity", 10),
                      ("EmergencyStop", 11),
                      ("VelocityError", 12),
                      ("ExternalInput", 15),
                      ("MotorTemperature", 17),
                      ("AmplifierTemperature", 18),
                      ("Encoder", 19),
                      ("Communication", 20),
                      ("FeedbackScaling", 23),
                      ("MarkerSearch", 24),
                      ("VoltageClamp", 27),
                      ("PowerSupply", 28),
                      ("Internal", 30)
                     )
    
    def __init__(self,*args,**kwargs):
        Controller.__init__(self,*args,**kwargs)
        self._comm = None
        
    def initialize(self):
        config = self.config.config_dict
        opt = {'port':8000, 'eol':'\n'}
        self._comm = get_comm(config, ctype=TCP, **opt)
        self._aero_axis = {}
        self._aero_speed = {}
        self._aero_acc= {}
        self._aero_enc = {}
        self._aero_state = AxisState()
        self._aero_state.create_state("EXTDISABLE", "External disable signal")
        self._aero_state.create_state("EXTSTOP", "Emergency stop button pressed")
        self._aero_state.create_state("HOMEDONE", "Homing done")
        self._debug_flag = False

    def initialize_hardware(self):
        self.raw_write("ACKNOWLEDGEALL")
        self.raw_write("RAMP MODE RATE")
        self.raw_write("WAIT MODE NOWAIT")

    def initialize_axis(self, axis):
        if axis.name not in self._aero_axis.keys():
            aero_name = axis.config.get("aero_name", str, "X")
            if aero_name in self._aero_axis.values():
                others= [ name for name in self._aero_axis 
                          if self._aero_axis[name] == aero_name ]
                raise ValueError("Aero Axis [%s] already defined for [%s]"%\
                                 (aero_name, string.join(others, ",")))
            self._aero_axis[axis.name]= aero_name

    def initialize_hardware_axis(self, axis):
        self.set_on(axis)
     
    def _debug(self, mesg): 
        if self._debug_flag:
            print time.time(), ">>", mesg

    def raw_write(self, cmd):
        self._debug("SEND "+cmd)
        send_cmd = cmd + self.CMD_TERM
        self._comm.write(send_cmd)
        reply = self._comm.read(size=1)
        self._debug("GET "+reply)
        self._check_reply_code(reply, cmd)

    def _check_reply_code(self, reply, cmd):
        if reply != self.RET_SUCCESS:
            if reply == self.RET_INVALID:
                raise ValueError("Aero Invalid command [%s]"%cmd)
            elif reply == self.RET_FAULT:
                raise ValueError("Aero Command error [%s]"%cmd)
            elif reply ==self.RET_TIMEOUT:
                raise ValueError("Aero Timeout on command [%s]"%cmd)
            else:
                raise ValueError("Aero Unknown command error")
        return 1

    def raw_write_read(self, cmd):
        self.raw_write(cmd)
        reply = self._comm.readline()
        self._debug("READ "+reply)
        return reply

    def _aero_name(self, axis):
        return self._aero_axis[axis.name]
  
    def clear_error(self, axis):
        self.raw_write("FAULTACK %s"%self._aero_name(axis))
 
    def read_status(self, axis):
        status= self.raw_write_read("AXISSTATUS(%s)"%self._aero_name(axis))
        axis_status = AerotechStatus(int(status), self.AXIS_STATUS_BITS)

        fault = self.raw_write_read("AXISFAULT(%s)"%self._aero_name(axis))
        axis_fault = AerotechStatus(int(fault), self.AXIS_FAULT_BITS)

        if int(fault) > 0 and not axis_status.MoveActive:
            self.clear_error(axis)
            fault = self.raw_write_read("AXISFAULT(%s)"%self._aero_name(axis))
            axis_fault = AerotechStatus(int(fault), self.AXIS_FAULT_BITS)

        return (axis_fault, axis_status)

    def state(self, axis):
        state = self._aero_state.new()

        (aero_fault, aero_status) = self.read_status(axis)

        if aero_fault.PositiveHardLimit or aero_fault.PositiveSoftLimit:
            state.set("LIMPOS")
        if aero_fault.NegativeHardLimit or aero_fault.NegativeSoftLimit:
            state.set("LIMNEG")
        if aero_status.HomeLimit:
            state.set("HOME")
        if aero_status.EmergencyStop:
            state.set("EXTSTOP")
        if aero_fault.ExternalInput:
            state.set("EXTDISABLE")
        if aero_status.Homed:
            state.set("HOMEDONE")

        if aero_fault.get() > 0:
            state.set("FAULT")
        else:
            if aero_status.Enabled:
                if aero_status.MoveActive or aero_status.Homing:
                    state.set("MOVING")
                else:
                    state.set("READY")
            else:
                state.set("OFF")

        return state
           
    def get_id(self, axis):
        version = self.raw_write_read("VERSION")
        return "Aerotech axis %s - version %s"%(self._aero_name(axis), version)

    def get_info(self, axis):
        idstr = self.get_id(axis)
        (fault, status) = self.read_status(axis)
        info = "%s\n\nAxis Status : 0x%08x\n%s\n\nAxis Fault : 0x%08x\n%s\n"%\
               (idstr, status.get(), str(status), fault.get(), str(fault))
        return info

    def set_on(self, axis):
        self.raw_write("ENABLE %s"%self._aero_name(axis))

    def set_off(self, axis):
        self.raw_write("DISABLE %s"%self._aero_name(axis))

    def start_one(self, motion):
        axis = motion.axis
        pos = motion.target_pos / axis.steps_per_unit
        aero_name = self._aero_name(axis)
        speed = self._aero_speed[axis.name]

        move_cmd = "%s %f"%(aero_name, pos)
        speed_cmd = "%sF %f"%(aero_name, speed)

        cmd = "MOVEABS %s %s"%(move_cmd, speed_cmd)
        self.raw_write(cmd)

    def start_all(self, *motion_list):
        moves = []
        speeds = []

        for motion in motion_list:
            axis = motion.axis
            pos = motion.target_pos / axis.steps_per_unit
            aero_name = self._aero_name(axis)
            speed = self._aero_speed[axis.name]

            moves.append("%s %f"%(aero_name, pos))
            speeds.append("%sF %f"%(aero_name, speed))

        move_cmd = string.join(moves, " ")
        speed_cmd = string.join(speeds, " ")

        cmd = "MOVEABS %s %s"%(move_cmd, speed_cmd)
        self.raw_write(cmd)

    def read_position(self, axis):
        reply = self.raw_write_read("CMDPOS(%s)"%self._aero_name(axis))
        pos = float(reply) * axis.steps_per_unit
        return pos

    def set_velocity(self, axis, new_vel):
        self._aero_speed[axis.name]= new_vel / abs(axis.steps_per_unit)
        
    def read_velocity(self, axis):
        speed = self._aero_speed[axis.name] * abs(axis.steps_per_unit)
        return speed

    def read_acceleration(self, axis):
        # reply = self.raw_write_read("GETMODE(7)")
        acc = self._aero_acc[axis.name] * abs(axis.steps_per_unit)
        return acc

    def set_acceleration(self, axis, new_acc):
        acc = new_acc / abs(axis.steps_per_unit)
        self.raw_write("RAMP RATE X %f"%acc)
        self._aero_acc[axis.name] = acc

    def stop(self, axis=None):
        if axis is not None:
            self.raw_write("ABORT %s"%self._aero_name(axis))
        else:
            self.raw_write("ABORT")

    def stop_all(self, *motion_list):
        axis_names = []
        for motion in motion_list:
            axis_names.append(self._aero_name(motion.axis))
        cmd = "ABORT " + string.join(axis_names, " ")
        self.raw_write(cmd)

    def home_search(self, axis, switch):
        cmd = "HOME %s"%self._aero_name(axis)
        self._debug("SEND "+cmd)
        send_cmd = cmd + self.CMD_TERM
        self._comm.write(send_cmd)

        homing= True
        while homing:
            try:
                reply = self._comm.read(size=1, timeout=1.0)
                self._debug("GET "+reply)
            except:
                reply = None

            if reply is not None:
                if self._check_reply_code(reply, cmd):
                    homing = False
            else:
                gevent.sleep(0.25)
            
    def home_state(self, axis):
        return AxisState("READY")
        
    def initialize_encoder(self, encoder):
        if encoder.name not in self._aero_enc.keys():
            aero_name = encoder.config.get("aero_name", str, None)
            if aero_name is None:
                raise ValueError("Missing aero_name key in %s encoder config"%encoder.name)
            self._aero_enc[encoder.name]= aero_name

    def _aero_encoder_axis(self, encoder):
        return self._aero_enc[encoder.name]

    def read_encoder(self, encoder):
        reply = self.raw_write_read("PFBK(%s)"%self._aero_encoder_axis(encoder))
        return float(reply)

