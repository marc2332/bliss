# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import gevent
import functools
from bliss.common.greenlet_utils import protect_from_kill
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.common.utils import object_method
from bliss.comm.tcp import Command
import struct
import numpy


class Icepap(Controller):
    """
    IcePAP stepper controller without Deep Technology of Communication.
    But if you prefer to have it (DTC) move to IcePAP controller class.
    Use this class controller at your own risk, because you won't
    have any support...
    """
    STATUS_DISCODE = {
        0 : ('POWERENA',      'power enabled'),                   
        1 : ('NOTACTIVE',     'axis configured as not active'),   
        2 : ('ALARM',         'alarm condition'),                 
        3 : ('REMRACKDIS',    'remote rack disable input signal'),
        4 : ('LOCRACKDIS',    'local rack disable switch'),       
        5 : ('REMAXISDIS',    'remote axis disable input signal'),
        6 : ('LOCAXISDIS',    'local axis disable switch'),       
        7 : ('SOFTDIS',       'software disable'),
    }

    STATUS_MODCODE = {
        0 : ('OPER',          'operation mode'),     
        1 : ('PROG',          'programmation mode'), 
        2 : ('TEST',          'test mode'),          
        3 : ('FAIL',          'fail mode'),
    }
    STATUS_STOPCODE = {
        0 : ('SCEOM',         'end of movement'),                 
        1 : ('SCSTOP',        'last motion was stopped'),         
        2 : ('SCABORT',       'last motion was aborted'),         
        3 : ('SCLIMPOS',      'positive limitswitch reached'),    
        4 : ('SCLINNEG',      'negative limitswitch reached'),    
        5 : ('SCSETTLINGTO',  'settling timeout'),                
        6 : ('SCAXISDIS',     'axis disabled (no alarm)'),        
        7 : ('SCBIT7',        'n/a'),                             
        8 : ('SCINTFAIL',     'internal failure'),                
        9 : ('SCMOTFAIL',     'motor failure'),                   
        10 : ('SCPOWEROVL',   'power overload'),                  
        11 : ('SCHEATOVL',    'driver overheating'),              
        12 : ('SCCLERROR',    'closed loop error'),               
        13 : ('SCCENCERROR',  'control encoder error'),           
        14 : ('SCBIT14',      'n/a'),                             
        15 : ('SCEXTALARM',   'external alarm'),
    }

    def __init__(self,*args,**kwargs):
        Controller.__init__(self,*args,**kwargs)
        self._cnx = None

    def initialize(self):
        hostname = self.config.get("host")
        self._cnx = Command(hostname,5000,eol='\n')

        self._icestate = AxisState()
        self._icestate.create_state("POWEROFF", "motor power is off")
        for codes in (self.STATUS_DISCODE,self.STATUS_MODCODE,self.STATUS_STOPCODE):
            for state,desc in codes.values():
                self._icestate.create_state(state,desc)

    def initialize_axis(self,axis):
        axis.address = axis.config.get("address",int)

    def initialize_hardware_axis(self,axis):
        try:
            self.set_on(axis)
        except:
            sys.excepthook(*sys.exc_info())

    #Axis power management 
    def set_on(self,axis):
        """
        Put the axis power on
        """
        self._power(axis,True)

    def set_off(self,axis):
        """
        Put the axis power off
        """
        self._power(axis,False)

    def _power(self,axis,power):
        _ackcommand(self._cnx,"POWER %s %d" % 
                    ("ON" if power else "OFF",axis.address))

    def read_position(self,axis):
        return int(_command(self._cnx,"?FPOS %d" % axis.address))
    
    def set_position(self,axis,new_pos):
        _ackcommand(self._cnx,"POS %d %d" % (axis.address,_round(new_pos)))
        return self.read_position(axis)

    def read_velocity(self,axis):
        return float(_command(self._cnx,"?VELOCITY %d" % axis.address))

    def set_velocity(self,axis,new_velocity):
        _ackcommand(self._cnx,"VELOCITY %d %f" % 
                    (axis.address,new_velocity))
        return self.read_velocity(axis)

    def read_acceleration(self,axis):
        acctime = float(_command(self._cnx,"?ACCTIME %d" % axis.address))
        velocity = self.read_velocity(axis)
        return velocity/float(acctime)

    def set_acceleration(self,axis,new_acc):
        velocity = self.read_velocity(axis)
        new_acctime = velocity/new_acc

        _ackcommand(self._cnx,"ACCTIME %d %f" % (axis.address,new_acctime))
        return self.read_acceleration(axis)

    def state(self,axis):
        status = int(_command(self._cnx,"?FSTATUS %d" % (axis.address)),16)
        status ^= 1<<23 #neg POWERON FLAG
        state = self._icestate.new()
        for mask,value in (((1<<9),"READY"),
                           ((1<<10|1<<11),"MOVING"),
                           ((1<<18),"LIMPOS"),
                           ((1<<19),"LIMNEG"),
                           ((1<<20),"HOME"),
                           ((1<<23),"POWEROFF")):
            if status & mask:
                state.set(value)

        state_mode = (status >> 2) & 0x3
        if state_mode:
            state.set(self.STATUS_MODCODE.get(state_mode)[0])

        stop_code = (status >> 14) & 0xf
        if stop_code:
            state.set(self.STATUS_STOPCODE.get(stop_code)[0])

        disable_condition = (status >> 4) & 0x7
        if disable_condition:
            state.set(self.STATUS_DISCODE.get(disable_condition)[0])

        if state.READY:
            #if motor is ready then no need to investigate deeper
            return state

        if not state.MOVING:
            # it seems it is not safe to call warning and/or alarm commands
            # while homing motor, so let's not ask if motor is moving
            if status & (1<<13):
                warning = _command(self._cnx,"?WARNING %d" % axis.address)
                warn_str =  "warning condition: \n" + warning
                status.create_state("WARNING",warn_str)
                status.set("WARNING")

            try:
                alarm = _command(self._cnx,"?ALARM %d" % axis.address)
            except RuntimeError:
                pass
            else:
                if alarm != "NO":
                    alarm_dsc = "alarm condition: " + str(alarm)
                    state.create_state("ALARMDESC",alarm_dsc)
                    state.set("ALARMDESC")

        return state

    def get_info(self,axis):
        pre_cmd = '%d:' % axis.address
        r =  "MOTOR   : %s\n" % axis.name
        r += "SYSTEM  : %s (ID: %s) (VER: %s)\n" % (self._cnx._host,
                                                    _command(self._cnx,"0:?ID"),
                                                    _command(self._cnx,"?VER"))
        r += "DRIVER  : %d\n" % axis.address
        r += "POWER   : %s\n" % _command(self._cnx,pre_cmd + "?power")
        r += "CLOOP   : %s\n" % _command(self._cnx,pre_cmd + "?pcloop")
        r += "WARNING : %s\n" % _command(self._cnx,pre_cmd + "?warning")
        r += "ALARM   : %s\n" % _command(self._cnx,pre_cmd + "?alarm")
        return r
    
    def raw_write(self,message,data = None):
        return _command(self._cnx,message,data)
        
    def raw_write_read(self,message,data = None):
        return _ackcommand(self._cnx,message,data)

    def prepare_move(self,motion):
        pass

    def start_one(self,motion):
        _ackcommand(self._cnx,"MOVE %d %d" % (motion.axis.address,
                                              motion.target_pos))

    def start_all(self,*motions):
        if motions > 1:
            cmd = "MOVE GROUP "
            cmd += ' '.join(["%d %d" % (m.axis.address,m.target_pos) for m in motions])
            _ackcommand(self._cnx,cmd)
        elif motions:
            self.start_one(motions[0])

    def stop(self,axis):
        _command(self._cnx,"STOP %d" % axis.address)

    def stop_all(self,*motions):
        for motion in motions:
            self.stop(motion.axis)

    def home_search(self,axis,switch):
        cmd = "HOME " + ("+1" if switch > 0 else "-1")
        _ackcommand(self._cnx,"%d:%s" % (axis.address,cmd))
        # IcePAP status is not immediately MOVING after home search command is sent
        gevent.sleep(0.2)

    def home_state(self,axis):
        return self.state(axis)

    def limit_search(self,axis,limit):
        cmd = "SRCH LIM" + ("+" if limit>0 else "-")
        _ackcommand(self._cnx,"%d:%s" % (axis.address,cmd))
        # TODO: MG18Nov14: remove this sleep (state is not immediately MOVING)
        gevent.sleep(0.1)

    def initialize_encoder(self,encoder):
        # Get axis config from bliss config
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        encoder.address = encoder.config.get("address", int)

        # Get optional encoder input to read
        enctype = encoder.config.get("type",str,"ENCIN").upper()
        # Minium check on encoder input
        if enctype not in ['ENCIN', 'ABSENC', 'INPOS', 'MOTOR', 'AXIS', 'SYNC']:
            raise ValueError('Invalid encoder type')
        encoder.enctype = enctype

    def read_encoder(self,encoder):
        value = _command(self._cnx,"?ENC %s %d" % (encoder.enctype,encoder.address))
        return int(value)

    def set_encoder(self,encoder,steps):
        _ackcommand(self._cnx,"ENC %s %d %d" % (encoder.enctype,encoder.address,steps))

    @object_method(types_info=("bool","bool"))
    def activate_closed_loop(self,axis,active):
        _command(self._cnx,"#%d:PCLOOP %s" % (axis.address,"ON" if active else "OFF"))
        return active

    @object_method(types_info=("None","bool"))
    def is_closed_loop_activate(self,axis):
        return True if _command(self._cnx,"%d:?PCLOOP" % axis.address) == 'ON' else False

    @object_method(types_info=("None","None"))
    def reset_closed_loop(self,axis):
        measure_position = int(_command(self._cnx,"%d:?POS MEASURE" % axis.address))
        self.set_position(axis,measure_position)
        self.set_on(axis)
        axis.sync_hard()
        
    @object_method(types_info=("None","int"))
    def temperature(self,axis):
        return int(_command(self._cnx,"%d:?MEAS T" % axis.address))

    
    def reset(self):
        _command(self._cnx,"RESET")

    def mdspreset(self):
        """
        Reset the MASTER DSP
        """
        _command(self._cnx,"_dsprst")

    def reboot(self):
        _command(self._cnx,"REBOOT")
    
_check_reply = re.compile("^[#?]|^[0-9]+:\?")
@protect_from_kill
def _command(cnx,cmd,data = None):
    cmd = cmd.upper()
    if data is not None:
        uint16_view = data.view(dtype=numpy.uint16)
        data_checksum = uint16_view.sum()
        header = struct.pack("<III",
                             0xa5aa555a, # Header key
                             len(uint16_view),int(data_checksum) & 0xffffffff)

        data_test = data.newbyteorder('<')
        if len(data_test) and data_test[0] != data[0]: # not good endianness
            data = data.byteswap()

        full_cmd = "%s\n%s%s" % (cmd,header,data.tostring())
        transaction = cnx._write(full_cmd)
    else:
        transaction = cnx._write(cmd + '\n')
    with cnx.Transaction(cnx,transaction) :
        if _check_reply.match(cmd):
            msg = cnx._readline(transaction=transaction,
                                clear_transaction=False)
            cmd = cmd.strip('#').split(' ')[0]
            msg = msg.replace(cmd + ' ','')
            if msg.startswith('$'):
                msg = cnx._readline(transaction=transaction,
                                    clear_transaction=False,eol='$\n')
            elif msg.startswith('ERROR'):
                raise RuntimeError(msg.replace('ERROR ',''))
            return msg.strip(' ')

def _ackcommand(cnx,cmd,data = None):
    if not cmd.startswith('#') and not cmd.startswith('?'):
        cmd = '#' + cmd
    return _command(cnx,cmd,data)

def _round(x):
    return round(x+0.5 if x >= 0 else x-0.5)

from .shutter import Shutter
from .switch import Switch
