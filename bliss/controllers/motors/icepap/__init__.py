# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import time
import gevent
import functools
from bliss.common.greenlet_utils import protect_from_kill
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState,Axis
from bliss.common.utils import object_method
from bliss.comm.tcp import Command
import struct
import numpy
import sys


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
        self._last_axis_power_time = dict()

    def initialize(self):
        hostname = self.config.get("host")
        self._cnx = Command(hostname,5000,eol='\n')

        self._icestate = AxisState()
        self._icestate.create_state("POWEROFF", "motor power is off")
        for codes in (self.STATUS_DISCODE,self.STATUS_MODCODE,self.STATUS_STOPCODE):
            for state,desc in codes.values():
                self._icestate.create_state(state,desc)

    def finalize(self):
        if self._cnx is not None:
            self._cnx.close()
            
    def initialize_axis(self,axis):
        axis.address = axis.config.get("address",lambda x: x)

        if hasattr(axis,'_init_software'):
            axis._init_software()

    def initialize_hardware_axis(self,axis):
        if axis.config.get('autopower', converter=bool, default=True):
            try:
                self.set_on(axis)
            except:
                sys.excepthook(*sys.exc_info())

        if hasattr(axis,'_init_hardware'):
            axis._init_hardware()

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
        _ackcommand(self._cnx,"POWER %s %s" % 
                    ("ON" if power else "OFF",axis.address))
        self._last_axis_power_time[axis] = time.time()

    def read_position(self,axis,cache=True):
        pos_cmd = "FPOS" if cache else "POS"
        return int(_command(self._cnx,"?%s %s" % (pos_cmd,axis.address)))
    
    def set_position(self,axis,new_pos):
        if isinstance(axis,SlaveAxis):
            pre_cmd = "%d:DISPROT LINKED;" % axis.address
        else:
            pre_cmd = None
        _ackcommand(self._cnx,"POS %s %d" % (axis.address,int(round(new_pos))),
                    pre_cmd = pre_cmd)
        return self.read_position(axis,cache=False)

    def read_velocity(self,axis):
        return float(_command(self._cnx,"?VELOCITY %s" % axis.address))

    def set_velocity(self,axis,new_velocity):
        _ackcommand(self._cnx,"VELOCITY %s %f" % 
                    (axis.address,new_velocity))
        return self.read_velocity(axis)

    def read_acceleration(self,axis):
        acctime = float(_command(self._cnx,"?ACCTIME %s" % axis.address))
        velocity = self.read_velocity(axis)
        return velocity/float(acctime)

    def set_acceleration(self,axis,new_acc):
        velocity = self.read_velocity(axis)
        new_acctime = velocity/new_acc

        _ackcommand(self._cnx,"ACCTIME %s %f" % (axis.address,new_acctime))
        return self.read_acceleration(axis)

    def state(self,axis):
        last_power_time = self._last_axis_power_time.get(axis,0)
        if time.time() - last_power_time < 1.:
            status_cmd = "?STATUS"
        else:
            self._last_axis_power_time.pop(axis,None)
            status_cmd = "?FSTATUS"

        status = int(_command(self._cnx,"%s %s" %
                              (status_cmd,axis.address)),16)
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
                try:
                    warning = _command(self._cnx,"%d:?WARNING" % axis.address)
                except TypeError:
                    pass
                else:
                    warn_str =  "Axis %s warning condition: \n" % axis.name
                    warn_str +=  warning
                    state.create_state("WARNING",warn_str)
                    state.set("WARNING")

            try:
                alarm = _command(self._cnx,"%d:?ALARM" % axis.address)
            except (RuntimeError,TypeError):
                pass
            else:
                if alarm != "NO":
                    alarm_dsc = "alarm condition: " + str(alarm)
                    state.create_state("ALARMDESC",alarm_dsc)
                    state.set("ALARMDESC")

        return state

    def get_info(self,axis):
        pre_cmd = '%s:' % axis.address
        r =  "MOTOR   : %s\n" % axis.name
        r += "SYSTEM  : %s (ID: %s) (VER: %s)\n" % (self._cnx._host,
                                                    _command(self._cnx,"0:?ID"),
                                                    _command(self._cnx,"?VER"))
        r += "DRIVER  : %s\n" % axis.address
        r += "POWER   : %s\n" % _command(self._cnx,pre_cmd + "?POWER")
        r += "CLOOP   : %s\n" % _command(self._cnx,pre_cmd + "?PCLOOP")
        r += "WARNING : %s\n" % _command(self._cnx,pre_cmd + "?WARNING")
        r += "ALARM   : %s\n" % _command(self._cnx,pre_cmd + "?ALARM")
        return r
    
    def raw_write(self,message,data = None):
        return _command(self._cnx,message,data)
        
    def raw_write_read(self,message,data = None):
        return _ackcommand(self._cnx,message,data)

    def prepare_move(self,motion):
        pass

    def start_one(self,motion):
        if isinstance(motion.axis,SlaveAxis):
            pre_cmd = "%d:DISPROT LINKED;" % motion.axis.address
        else:
            pre_cmd = None

        _ackcommand(self._cnx,"MOVE %s %d" % (motion.axis.address,
                                              motion.target_pos),
                    pre_cmd = pre_cmd)

    def start_all(self,*motions):
        if motions > 1:
            cmd = "MOVE GROUP "
            cmd += ' '.join(["%s %d" % (m.axis.address,m.target_pos) for m in motions])
            _ackcommand(self._cnx,cmd)
        elif motions:
            self.start_one(motions[0])

    def stop(self,axis):
        _command(self._cnx,"STOP %s" % axis.address)

    def stop_all(self,*motions):
        axes_addr = ' '.join('%s' % m.axis.address for m in motions)
        _command(self._cnx,"STOP %s" % axes_addr)

    def home_search(self,axis,switch):
        cmd = "HOME " + ("+1" if switch > 0 else "-1")
        _ackcommand(self._cnx,"%s:%s" % (axis.address,cmd))
        # IcePAP status is not immediately MOVING after home search command is sent
        gevent.sleep(0.2)

    def home_state(self,axis):
        s = self.state(axis)
        if s != 'READY' and s != 'POWEROFF':
             s.set('MOVING')
        return s

    def limit_search(self,axis,limit):
        cmd = "SRCH LIM" + ("+" if limit>0 else "-")
        _ackcommand(self._cnx,"%s:%s" % (axis.address,cmd))
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
        _ackcommand(self._cnx,"ENC %s %d %d" % 
                    (encoder.enctype,encoder.address,steps))

    def set_event_positions(self,axis_or_encoder,positions):
        int_position = numpy.array(positions,dtype=numpy.int32)
        #position has to be ordered
        int_position.sort()
        address = axis_or_encoder.address
        if not len(int_position):
            _ackcommand(self._cnx,"%s:ECAMDAT CLEAR" % address)
            return

        if isinstance(axis_or_encoder,Axis):
            source = 'AXIS'
        else:                   # encoder
            source = 'MEASURE'

        #load trigger positions
        _ackcommand(self._cnx,"%s:*ECAMDAT %s DWORD" % (address,source),
                    int_position)
         # send the trigger on the multiplexer
        _ackcommand(self._cnx,"%s:SYNCAUX eCAM" % address)

    def get_event_positions(self,axis_or_encoder):
        """
        For this controller this method should be use
        for debugging purposed only... 
        """
        address = axis_or_encoder.address
        #Get the number of positions
        reply = _command(self._cnx,"%d:?ECAMDAT" % address)
        reply_exp = re.compile("(\w+) +([+-]?\d+) +([+-]?\d+) +(\d+)")
        m = reply_exp.match(reply)
        if m is None:
            raise RuntimeError("Reply Didn't expected: %s" % reply)
        source = m.group(1)
        nb = int(m.group(4))
        
        if isinstance(axis_or_encoder,Axis):
            nb = nb if source == 'AXIS' else 0
        else:                   # encoder
            nb = nb if source == "MEASURE" else 0

        positions = numpy.zeros((nb,),dtype = numpy.int32)
        if nb > 0:
            reply_exp = re.compile(".+: +([+-]?\d+)")
            reply = _command(self._cnx,"%d:?ECAMDAT %d" % (address,nb))
            for i,line in enumerate(reply.split('\n')):
                m = reply_exp.match(line)
                if m:
                    pos = int(m.group(1))
                    positions[i] = pos
        return positions

    def get_linked_axis(self):
        reply = _command(self._cnx,"?LINKED")
        linked = dict()
        for line in reply.strip().split('\n'):
            values = line.split()
            linked[values[0]] = [int(x) for x in values[1:]]
        return linked

    @object_method(types_info=("bool","bool"))
    def activate_closed_loop(self,axis,active):
        _command(self._cnx,"#%s:PCLOOP %s" % (axis.address,"ON" if active else "OFF"))
        return active

    @object_method(types_info=("None","bool"))
    def is_closed_loop_activate(self,axis):
        return True if _command(self._cnx,"%s:?PCLOOP" % axis.address) == 'ON' else False

    @object_method(types_info=("None","None"))
    def reset_closed_loop(self,axis):
        measure_position = int(_command(self._cnx,"%s:?POS MEASURE" % axis.address))
        self.set_position(axis,measure_position)
        if axis.config.get('autopower', converter=bool, default=True):
            self.set_on(axis)
        axis.sync_hard()
        
    @object_method(types_info=("None","int"))
    def temperature(self,axis):
        return int(_command(self._cnx,"%s:?MEAS T" % axis.address))

    @object_method(types_info=(("float","bool"),"None"))
    def set_tracking_positions(self,axis,positions,cyclic = False):
        """
        Send position to the controller which will be tracked.

        positions --  are expressed in user unit
        cyclic -- cyclic position or not default False

        @see activate_track method
        """
        address = axis.address
        if not len(positions):
            _ackcommand(self._cnx,"%s:LISTDAT CLEAR" % address)
            return

        dial_positions = axis.user2dial(numpy.array(positions, dtype=numpy.float))
        step_positions = numpy.array(dial_positions * axis.steps_per_unit,
                                     dtype=numpy.int32)
        _ackcommand(self._cnx,"%d:*LISTDAT %s DWORD" % 
                    (address, "CYCLIC" if cyclic else "NOCYCLIC"),
                    step_positions)

    @object_method(types_info=("None",("float","bool")))
    def get_tracking_positions(self,axis):
        """
        Get the tacking positions.
        This method should only be use for debugging
        return a tuple with (positions,cyclic flag)
        """
        address = axis.address
        #Get the number of positions
        reply = _command(self._cnx,"%d:?LISTDAT" % address)
        reply_exp = re.compile("(\d+) *(\w+)?")
        m = reply_exp.match(reply)
        if m is None:
            raise RuntimeError("Reply didn't expected: %s" % reply)
        nb = int(m.group(1))
        positions = numpy.zeros((nb,),dtype = numpy.int32)
        cyclic = True if m.group(2) == "CYCLIC" else False
        if nb > 0:
            reply_exp = re.compile(".+: +([+-]?\d+)")
            reply = _command(self._cnx,"%d:?LISTDAT %d" % (address,nb))
            for i,line in enumerate(reply.split('\n')):
                m = reply_exp.match(line)
                if m:
                    pos = int(m.group(1))
                    positions[i] = pos
            dial_positions = positions / axis.steps_per_unit
            positions = axis.dial2user(dial_positions)
        return positions,cyclic

    @object_method(types_info=(("bool","str"),"None"))
    def activate_tracking(self,axis,activate,mode = None):
        """
        Activate/Deactivate the tracking position depending on
        activate flag
        mode -- default "INPOS" if None.
        mode can be :
           - SYNC   -> Internal SYNC signal
           - ENCIN  -> ENCIN signal
           - INPOS  -> INPOS signal
           - ABSENC -> ABSENC signal
        """
        address = axis.address

        if not activate:
            _ackcommand(self._cnx,"STOP %d" % address)
            axis.sync_hard()
        else:
            if mode is None: mode = "INPOS"
            possibles_modes = ["SYNC","ENCIN","INPOS","ABSENC"]
            if mode not in possibles_modes:
                raise ValueError("mode %s is not managed, can only choose %s" % 
                                 (mode,possibles_modes))
            if mode == "INPOS":
                _ackcommand(self._cnx, "%d:POS INPOS 0" % address)
            _ackcommand(self._cnx,"%d:LTRACK %s" % (address,mode))
        
    @object_method(types_info=("float", "None"))
    def blink(self, axis, second=3.):
        """
        Blink axis driver
        """
        _command(self._cnx,"%d:BLINK %f" % (axis.address, second))

    def reset(self):
        _command(self._cnx,"RESET")

    def mdspreset(self):
        """
        Reset the MASTER DSP
        """
        _command(self._cnx,"_dsprst")

    def reboot(self):
        _command(self._cnx,"REBOOT")
        self._cnx.close()

_check_reply = re.compile("^[#?]|^[0-9]+:\?")
@protect_from_kill
def _command(cnx,cmd,data = None,pre_cmd = None):
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
        full_cmd = "%s%s\n" % (pre_cmd or '',cmd)
        transaction = cnx._write(full_cmd)
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

def _ackcommand(cnx,cmd,data = None,pre_cmd = None):
    if not cmd.startswith('#') and not cmd.startswith('?'):
        cmd = '#' + cmd
    return _command(cnx,cmd,data,pre_cmd)

from .shutter import Shutter
from .switch import Switch
from .linked import LinkedAxis, SlaveAxis
