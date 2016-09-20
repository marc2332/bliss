#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Bliss axis TANGO_ DS class (:class:`BlissAxisManager` and :class:`BlissAxis`)
'''

import bliss
import bliss.config.motors as bliss_config
import bliss.common.log as elog
from bliss.common import event
from bliss.common.utils import grouped

import PyTango
from PyTango.server import Device, DeviceMeta, device_property
from PyTango.server import attribute, command, get_worker

PyTango.requires_pytango('8.1.9', software_name='BlissAxis')

import os
import sys
import time
import traceback
import types
import json
import itertools

import gevent
from gevent.backdoor import BackdoorServer

import six

try:
    from bliss.config.conductor.connection import ConnectionException
except:
    print "beacon not installed ?"

    class ConnectionException(Exception):
        pass

from bliss.controllers.motor_group import Group


class bcolors:
    PINK = '\033[95m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    ENDC = '\033[0m'

types_conv_tab_inv = {
    PyTango.DevVoid: 'None',
    PyTango.DevDouble: 'float',
    PyTango.DevString: 'str',
    PyTango.DevLong: 'int',
    PyTango.DevBoolean: 'bool',
    PyTango.DevVarFloatArray: "float_array",
    PyTango.DevVarDoubleArray: "double_array",
    PyTango.DevVarLongArray: "long_array",
    PyTango.DevVarStringArray: "string_array",
    PyTango.DevVarBooleanArray: "bool_array",
}

types_conv_tab = dict((v, k) for k, v in types_conv_tab_inv.items())
types_conv_tab.update({
    None: PyTango.DevVoid,
    str: PyTango.DevString,
    int: PyTango.DevLong,
    float: PyTango.DevDouble,
    bool: PyTango.DevBoolean,
})

access_conv_tab = {
    'r': PyTango.AttrWriteType.READ,
    'w': PyTango.AttrWriteType.WRITE,
    'rw': PyTango.AttrWriteType.READ_WRITE,
}

access_conv_tab_inv = dict((v, k) for k, v in access_conv_tab.items())

@six.add_metaclass(DeviceMeta)
class BlissAxisManager(Device):

    BackdoorPort = device_property(dtype=int, default_value=None,
                                   doc='gevent Backdoor port')

    def delete_device(self):
        self.debug_stream("In delete_device() of controller")

    def init_device(self):
        Device.init_device(self)
        self.debug_stream("In init_device() of controller")
        self.group_dict = {}
        if self.BackdoorPort:
            print "Starting Backdoor server on port", self.BackdoorPort
            server = BackdoorServer(('127.0.0.1', self.BackdoorPort),
                                    banner="BlissAxisManager back door",
                                    locals={'axis_manager': self})
            gevent.spawn(server.serve_forever)
            self.__backdoor_server = server

    def _get_axis_devices(self):
        util = PyTango.Util.instance()
        dev_list = util.get_device_list("*")
        result = dict()
        for dev in dev_list:
            dev_class = dev.get_device_class()
            if dev_class:
                class_name = dev_class.get_name()
                if class_name.startswith("BlissAxis_"):
                    axis = dev.axis
                    result[axis.name] = dev
        return result

    def dev_state(self):
        """ This command gets the device state (stored in its device_state
        data member) and returns it to the caller.

        :param : none
        :type: PyTango.DevVoid
        :return: Device state
        :rtype: PyTango.CmdArgType.DevState """
#        self.debug_stream("In BlissAxisManager dev_state()")
        argout = PyTango.DevState.UNKNOWN

        # [BlissAxisManager(id26/bliss/cyrtest),
        # BlissAxis_robd(id26/bliss_cyrtest/robd),
        # BlissAxis_robc(id26/bliss_cyrtest/robc),
        # BlissAxis_robb(id26/bliss_cyrtest/robb),
        # BlissAxis_roba(id26/bliss_cyrtest/roba),
        # DServer(dserver/BlissAxisManager/cyrtest)]

        # Builds the BlissAxisManager State from states of BlissAxis devices.
        _bliss_working = True
        _bliss_moving = False

        devs = self._get_axis_devices().values()

        for dev in devs:
            _axis_state = dev.get_state()

            _axis_on = (_axis_state == PyTango.DevState.ON or _axis_state == PyTango.DevState.OFF)
            _axis_moving = (_axis_state == PyTango.DevState.MOVING)

            _axis_working = _axis_on or _axis_moving
            _bliss_working = _bliss_working and _axis_working
            _bliss_moving = _bliss_moving or _axis_moving

        if _bliss_moving:
            self.set_state(PyTango.DevState.MOVING)
        elif _bliss_working:
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("FAULT ???")

        # Builds the status for BlissAxisManager device from BlissAxis status
        E_status = ""
        for dev in devs:
            E_status = E_status + dev.get_name() + ":" + dev.get_state().name + ";" + dev.get_status() + "\n"
        self.set_status(E_status)

        return self.get_state()

    @command(dtype_out=[str], doc_out='list of axis')
    def GetAxisList(self):
        """
        Returns the list of BlissAxisManager axes of this device.
        """
        return [dev.get_name() for dev in self._get_axis_devices().values()]

    @command(dtype_in=[str], doc_in='Flat list of pairs motor, position',
             dtype_out=str, doc_out='group identifier')
    def GroupMove(self, axes_pos):
        """
        Absolute move multiple motors
        """
        axes_dict = self._get_axis_devices()
        axes_names = axes_pos[::2]
        if not set(axes_names).issubset(set(axes_dict)):
            raise ValueError("unknown axis(es) in motion")
        axes = [axes_dict[name].axis for name in axes_names]
        group = Group(*axes)
        event.connect(group, 'move_done', self.group_move_done)
        positions = map(float, axes_pos[1::2])
        axes_pos_dict = dict(zip(axes, positions))
        group.move(axes_pos_dict, wait=False)
        groupid = ','.join(map(':'.join, grouped(axes_pos, 2)))
        self.group_dict[groupid] = group
        return groupid

    def group_move_done(self, move_done, **kws):
        if not move_done:
            return
        elif not self.group_dict:
            print 'BlissAxisManager: move_done event with no group'
            return
        
        if 'sender' in kws:
            sender = kws['sender']
            groupid = [gid for gid, grp in self.group_dict.items()
                       if grp == sender][0]
        elif len(self.group_dict) == 1:
            groupid = self.group_dict.keys()[0]
        else:
            print 'BlissAxisManager: Warning: ' \
                  'cannot not identify group move_done'
            return

        self.group_dict.pop(groupid)

    @command(dtype_in=str, doc_in='group identifier',
             dtype_out=[str], doc_out='"flat list of pairs motor, status')
    def GroupState(self, groupid):
        """
        Return the individual state of motors in the group
        """
        if groupid not in self.group_dict:
            return []
        group = self.group_dict[groupid]
        def get_name_state_list(group):
            return [(name, str(axis.state()))
                    for name, axis in group.axes.items()]
        name_state_list = get_name_state_list(group)
        return list(itertools.chain(*name_state_list))

    @command(dtype_in=str, doc_in='group identifier')
    def GroupAbort(self, groupid):
        """
        Abort motor group movement
        """
        if groupid not in self.group_dict:
            return
        group = self.group_dict[groupid]
        group.stop(wait=False)

    def _reload(self):
        bliss_config.beacon_get_config().reload()

    @command
    def ReloadConfig(self):
        self._reload()

    @command(dtype_in=bool, doc_in='reload (true to do a reload before ' \
             'apply configuration, false not to)')
    def ApplyConfig(self, reload):
        if reload:
            self._reload()
        for dev in self._get_axis_devices().values():
            dev.axis.apply_config(reload=False)


# Device States Description
# ON : The motor powered on and is ready to move.
# MOVING : The motor is moving
# FAULT : The motor indicates a fault.
# ALARM : The motor indicates an alarm state for example has reached
# a limit switch.
# OFF : The power on the moror drive is switched off.
# DISABLE : The motor is in slave mode and disabled for normal use
@six.add_metaclass(DeviceMeta)
class BlissAxis(Device):

    write_position_wait = device_property(dtype=bool, default_value=False,
                                          doc='Write position waits for end of motion')

    def __init__(self, cl, name):
        self._axis_name = name.split('/')[-1]
        self._ds_name = name
        Device.__init__(self, cl, name)
        self.debug_stream("In __init__() of axis")

    @property
    def axis(self):
        self.__axis = bliss.get_axis(self._axis_name)
        return self.__axis

    def delete_device(self):
        self.debug_stream("In delete_device() of axis")

    def init_device(self):
        self.debug_stream("In init_device() of axis")
        Device.init_device(self)

        # -v1
        self.info_stream("INFO STREAM ON ++++++++++++++++++++++++++")
        self.warn_stream("WARN STREAM ON ++++++++++++++++++++++++++")
        self.error_stream("ERROR STREAM ON ++++++++++++++++++++++++++")
        self.fatal_stream("FATAL STREAM ON ++++++++++++++++++++++++++")

        # -v3 (-v == -v4)
        self.debug_stream("DEBUG STREAM ON ++++++++++++++++++++++++++")

        # force a get of axis and controller to update status in case of error
        try:
            axis = self.axis
            controller = self.axis.controller
        except:
            traceback.print_exc()
            elog.error("unable to get kontroller or axis")
            self.set_status(traceback.format_exc())
            _ctrl = 'UNKNOWN'
        else:
            m_attr = self.get_device_attr()
            try:
                m_attr.get_attr_by_name('Position').set_write_value(axis.position())
            except:
                pass
            try:
                m_attr.get_attr_by_name('Velocity').set_write_value(axis.velocity())
            except:
                pass
            _ctrl = controller.get_class_name()

        self.debug_stream("axis found : %s" % self._axis_name)

        self._init_time = time.time()
        self._t = time.time()

        self.attr_Home_position_read = 0.0
        self.attr_StepSize_read = 0.0
        self.attr_Steps_per_unit_read = 0.0
        self.attr_Acceleration_read = 1.0
        self.attr_HardLimitLow_read = False
        self.attr_HardLimitHigh_read = False
        self.attr_Backlash_read = 0.0
        self.attr_Sign_read = 1
        self.attr_Offset_read = 0.0
        self.attr_Tolerance_read = 0.0
        self.attr_PresetPosition_read = 0.0
        self.attr_FirstVelocity_read = 0.0

        """
        self.attr_Steps_read = 0
        self.attr_Position_read = 0.0
        self.attr_Measured_Position_read = 0.0
        self.attr_Home_side_read = False
        """

        self.attr_trajpar_read = [[0.0]]

        # To force update of state and status.
        self._dev_state()

        # elog.info("    %s" % self.axis.get_info())

        elog.info("BlissAxisManager [%s] : \t" % _ctrl + bcolors.PINK + self._ds_name + bcolors.ENDC + "\t initialized")

    def dev_state(self):
        return get_worker().execute(self._dev_state)

    def _dev_state(self):
        """ This command gets the device state (stored in its device_state
        data member) and returns it to the caller.

        :param : none
        :type: PyTango.DevVoid
        :return: Device state
        :rtype: PyTango.CmdArgType.DevState """
#        self.debug_stream("In AmotionAxis dev_state()")
        argout = PyTango.DevState.UNKNOWN

        try:
            _state = self.axis.state()

            if _state.READY:
                self.set_state(PyTango.DevState.ON)
            elif _state.MOVING:
                self.set_state(PyTango.DevState.MOVING)
            elif _state.OFF:
                self.set_state(PyTango.DevState.OFF)
            else:
                self.set_state(PyTango.DevState.FAULT)

            self.set_status(_state.current_states())

            self.attr_HardLimitLow_read = _state.LIMNEG
            self.attr_HardLimitHigh_read = _state.LIMPOS

        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status(traceback.format_exc())

        if argout != PyTango.DevState.ALARM:
            Device.dev_state(self)

        # print "dev_state %s" % self.get_state()
        return self.get_state()

    def dev_status(self):
        # update current state AND status
        get_worker().execute(self._dev_state)

        # get the updated status as a string
        self._status = self.get_status()
        return self._status

    @property
    def axis(self):
        return bliss.get_axis(self._axis_name)

    @attribute(dtype=float, label='Steps per user unit', unit='steps/uu',
               format='%7.1f')
    def Steps_per_unit(self):
        self.debug_stream("In read_Steps_per_unit()")
        return self.axis.steps_per_unit

    @Steps_per_unit.write
    def Steps_per_unit(self, value):
        self.debug_stream("In write_Steps_per_unit()")
        # data = attr.get_write_value()
        elog.debug("Not implemented")

    @attribute(dtype=int, label='Steps', format='%6d',
               doc='number of steps in the step counter\n')
    def Steps(self):
        self.debug_stream("In read_Steps()")
        _spu = float(self.axis.steps_per_unit)
        _steps = _spu * self.axis.position()
        return int(round(_steps))

    @attribute(dtype=float, label='Position', unit='uu',
               format='%10.3f', doc='the desired motor position in user units.')
    def Position(self):
        self.debug_stream("In read_Position()")

        _t = time.time()

        if self.axis.is_moving:
            quality = PyTango.AttrQuality.ATTR_CHANGING
        else:
            quality = PyTango.AttrQuality.ATTR_VALID
        result = self.axis.position(), _t, quality

        _duration = time.time() - _t

        if _duration > 0.05:
            print "BlissAxisManager.py : {%s} read_Position : duration seems too long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)
        return result

    @Position.write
    def Position(self, new_position):
        """
        Sends movement command to BlissAxisManager axis.
        NB : take care to call WaitMove before sending another movement
        self.write_position_wait is a device property (False by default).
        """
        self.debug_stream("In write_Position()")

        self.set_state(PyTango.DevState.MOVING)
        self.axis.move(new_position, wait=self.write_position_wait)
        self.set_state(PyTango.DevState.ON)

    def is_position_allowed(self, req_type):
        try:
            if req_type == PyTango.AttReqType.WRITE_REQ:
                if self.get_state() == "MOVING":
                    return False
                else:
                    return True
            else:
                return True
        except:
            sys.excepthook(*sys.exc_info())

    @attribute(dtype=float, label='Measured position', unit='uu',
               format='%10.3f', doc='the measured motor position in user units')
    def Measured_Position(self):
        self.debug_stream("In read_Measured_Position()")
        _t = time.time()
        result = self.axis.measured_position()
        _duration = time.time() - _t

        if _duration > 0.01:
            print "BlissAxisManager.py : {%s} read_Measured_Position : duration seems long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)
        return result

    @attribute(dtype=float, label='Acceleration', unit='user units/s^2',
               format='%10.3f', doc='Acceleration of the motor in uu/s2')
    def Acceleration(self):
        _acc = self.axis.acceleration()
        self.debug_stream("In read_Acceleration(%f)" % float(_acc))
        return _acc

    @Acceleration.write
    def Acceleration(self, new_acc):
        self.debug_stream("In write_Acceleration(%f)" % new_acc)
        self.axis.acceleration(new_acc)

    @attribute(dtype=float, label='Acceleration time', unit='s',
               format='%10.6f', doc='the acceleration time of the motor (in seconds)')
    def AccTime(self):
        self.debug_stream("In read_AccTime()")
        _acc_time = self.axis.acctime()
        self.debug_stream("In read_AccTime(%f)" % float(_acc_time))
        return _acc_time

    @AccTime.write
    def AccTime(self, new_acctime):
        self.axis.acctime(new_acctime)
        self.debug_stream("In write_AccTime(%f)" % float(new_acctime))

    @attribute(dtype=float, label='Velocity', unit='unit/s', format='%10.3f',
               doc='The constant velocity of the motor')
    def Velocity(self):
        _vel = self.axis.velocity()
        self.debug_stream("In read_Velocity(%g)" % _vel)
        return _vel

    @Velocity.write
    def Velocity(self, new_velocity):
        self.debug_stream("In write_Velocity(%g)" % new_velocity)
        self.axis.velocity(new_velocity)

    @attribute(dtype=float, label='Backlash', unit='uu', format='%5.3f',
               doc='Backlash to be applied to each motor movement')
    def Backlash(self):
        self.debug_stream("In read_Backlash()")
        print 'bacl', self.axis.backlash
        return self.axis.backlash

    @attribute(dtype='int16', label='Sign', unit='unitless', format='%d',
               doc='Sign between dial and user: +/-1')
    def Sign(self):
        self.debug_stream("In read_Sign()")
        return self.axis.sign

    @attribute(dtype=float, label='Offset', unit='uu', format='%7.5f',
               doc='Offset between (sign*dial) and user')
    def Offset(self):
        self.debug_stream("In read_Offset()")
        return self.axis.offset

    @Offset.write
    def Offset(self, data):
        self.debug_stream("In write_Offset()")
        new_pos = self.axis.dial2user(self.axis.dial(), data)
        self.axis.position(new_pos)

    @attribute(dtype=float, label='Tolerance', unit='uu', format='%7.5f',
               doc='Tolerance between dial and user')
    def Tolerance(self):
        self.debug_stream("In read_Tolerance()")
        return self.axis.tolerance

    @Tolerance.write
    def Tolerance(self, new_tolerance):
        self.debug_stream("In write_Tolerance()")
        self.debug_stream("write tolerance %s" % new_tolerance)

    @attribute(dtype=float, label='Home position', unit='uu', format='%7.3f',
               doc='Position of the home switch',
               display_level=PyTango.DispLevel.EXPERT)
    def Home_Position(self):
        self.debug_stream("In read_Home_position()")
        return self.attr_Home_position_read

    @Home_Position.write
    def Home_position(self, new_home_position):
        self.debug_stream("In write_Home_position()")
        self.attr_Home_position_read = new_home_position

    @attribute(dtype=bool, label='low limit switch state')
    def HardLimitLow(self):
        self.debug_stream("In read_HardLimitLow()")
        # Update state and return cached value.
        self._dev_state()
        return self.attr_HardLimitLow_read

    @attribute(dtype=bool, label='up limit switch state')
    def HardLimitHigh(self):
        self.debug_stream("In read_HardLimitHigh()")
        # Update state and return cached value.
        self._dev_state()
        return self.attr_HardLimitHigh_read

    @attribute(dtype=float, label='Preset Position', unit='uu', format='%10.3f',
               doc='preset the position in the step counter',
               display_level=PyTango.DispLevel.EXPERT)
    def PresetPosition(self):
        self.debug_stream("In read_PresetPosition()")
        return self.attr_PresetPosition_read

    @PresetPosition.write
    def PresetPosition(self, new_preset_position):
        self.debug_stream("In write_PresetPosition(%g)" % new_preset_position)
        self.attr_PresetPosition_read = new_preset_position
        # NOTE MP: if using TANGO DS let's consider that there is
        # a smart client out there who is handling the user/offset.
        # Therefore don't the user position/offset of EMotion.
        # Which means: always keep dial position == user position
        self.axis.dial(new_preset_position / self.axis.sign)
        self.axis.position(new_preset_position)

    @attribute(dtype=float, label='first step velocity', unit='units/s',
               format='%10.3f', doc='number of unit/s for the first step and ' \
               'for the move reference', display_level=PyTango.DispLevel.EXPERT)
    def FirstVelocity(self):
        self.debug_stream("In read_FirstVelocity()")
        return self.attr_FirstVelocity_read
        #attr.set_value(self.axis.FirstVelocity())

    @FirstVelocity.write
    def write_FirstVelocity(self, new_first_velocity):
        self.debug_stream("In write_FirstVelocity()")
        self.attr_FirstVelocity_read = new_first_velocity
        # self.axis.FirstVelocity(data)

    @attribute(dtype=bool, doc='indicates if the axis is below or above ' \
               'the position of the home switch')
    def Home_side(self):
        self.debug_stream("In read_Home_side()")
        return self.attr_Home_side_read

    @attribute(dtype=float, 
               doc='Size of the relative step performed by the ' \
               'StepUp and StepDown commands.\nThe StepSize' \
               'is expressed in physical unit',
               display_level=PyTango.DispLevel.EXPERT)
    def StepSize(self):
        self.debug_stream("In read_StepSize()")
        return self.attr_StepSize_read

    @StepSize.write
    def StepSize(self, new_step_size):
        self.debug_stream("In write_StepSize()")
        self.attr_StepSize_read = new_step_size

    def read_attr_hardware(self, data):
        pass
        # self.debug_stream("In read_attr_hardware()")

    @attribute(dtype=[[float]], max_dim_x=1000, max_dim_y=5)
    def trajpar(self):
        self.debug_stream("In read_trajpar()")
        return self.attr_trajpar_read

    @trajpar.write
    def trajpar(self, new_trajpar):
        self.debug_stream("In write_trajpar()")

    @attribute(dtype=[float], unit='uu', format='%10.3f', max_dim_x=2,
               doc='Software limits expressed in physical unit',
               display_level=PyTango.DispLevel.EXPERT)
    def Limits(self):
        self.debug_stream("In read_Limits()")
        return self.axis.limits()

    @Limits.write
    def write_Limits(self, limits):
        self.debug_stream("In write_Limits()")
        low, high = limits
        self.axis.limits(low, high)
        self.axis.settings_to_config(velocity=False, acceleration=False)

    """
    Motor command methods
    """
    @command
    def On(self):
        """ Enable power on motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In On()")
        self.axis.on()

        if self.axis.state().READY:
            self.set_state(PyTango.DevState.ON)
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("ON command was not executed as expected.")

    @command
    def Off(self):
        """ Disable power on motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Off()")
        self.axis.off()
        if self.axis.state().OFF:
            self.set_state(PyTango.DevState.OFF)
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("OFF command was not executed as expected.")

    @command(dtype_in=int, doc_in='homing direction')
    def GoHome(self, argin):
        """
        Moves the motor to the home position given by a home switch.
        Searches home switch in POSITIVE direction if argin is 1.
        Searches home switch in NEGATIVE direction if argin is -1.
        """
        self.debug_stream("In GoHome(%d)" % argin)
        self.axis.home(switch=argin, wait=False)

    @command
    def GoHomeInversed(self):
        """
        Moves the motor to the home position given by a home switch.
        Searches home switch in NEGATIVE direction.
        """
        self.debug_stream("In GoHomeInversed()")
        self.axis.home(switch=-1, wait=False)

    @command
    def Abort(self):
        """ Stop immediately the motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Abort()")
        self.axis.stop(wait=False)

    @command
    def Stop(self):
        """ Stop gently the motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Stop()")
        self.axis.stop(wait=False)

    @command
    def StepUp(self):
        """ Performs a relative motion of ``stepSize`` in the forward
         direction.  StepSize is defined as an attribute of the
         device.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepUp(); stepsize=%f" % self.attr_StepSize_read)
        self.axis.rmove(self.attr_StepSize_read, wait=self.write_position_wait)

    @command
    def StepDown(self):
        """ Performs a relative motion of ``stepSize`` in the backward
         direction.  StepSize is defined as an attribute of the
         device.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepDown(); stepsize=%f" % self.attr_StepSize_read)
        self.axis.rmove(-self.attr_StepSize_read, wait=self.write_position_wait)

    @command(dtype_out=str)
    def GetInfo(self):
        """ provide information about the axis.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevString """
        self.debug_stream("In GetInfo()")
        return self.axis.get_info()

    @command(dtype_in=str, doc_in='raw command to be send to the axis. Be carefull!')
    def RawWrite(self, argin):
        """ Sends a raw command to the axis. Be carefull!

        :param argin: String with command
        :type: PyTango.DevString
        :return: None
        """
        self.debug_stream("In RawWrite()")

        return self.axis.controller.raw_write(argin)

    @command(dtype_in=str, doc_in='raw command to be send to the axis. Be carefull!',
             dtype_out=str, doc_out='answer returned by the controller')
    def RawWriteRead(self, argin):
        """ Sends a raw command to the axis and read the result.
        Be carefull!

        :param argin: String with command
        :type: PyTango.DevString
        :return: answer from controller.
        :rtype: PyTango.DevString """
        self.debug_stream("In RawWriteRead()")

        return self.axis.controller.raw_write_read(argin)

    @command(dtype_out=float, doc_out='controller raw position (used to manage discrepency)')
    def CtrlPosition(self):
        """ Returns raw axis position read by controller.

        :param argin: None
        :type: PyTango.DevVoid
        :return: answer from controller.
        :rtype: PyTango.DevFloat """
        self.debug_stream("In CtrlPosition()")

        return self.axis.read_position()

    @command
    def SyncHard(self):
        self.debug_stream("In SyncHard()")
        return self.axis.sync_hard()

    @command
    def WaitMove(self):
        """ Waits end of last motion

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In WaitMove()")
        return self.axis.wait_move()

    @command(dtype_in=str, doc_in='parameter name',
             dtype_out=str, doc_out='configuration value')
    def ReadConfig(self, argin):
        return self.axis.config.get(argin)

    @command(dtype_in=int, doc_in='state of the gate 0/1')
    def SetGate(self, argin):
        """
        Activate or de-activate gate of this axis.
        """
        self.debug_stream("In SetGate(%s)" % argin)

        return self.axis.set_gate(argin)

    @command(dtype_out=[str], doc_out='list of axis custom commands')
    def GetCustomCommandList(self):
        """
        Returns the list of custom commands.
        JSON format.
        """
        _cmd_list = self.axis.custom_methods_list

        argout = list()

        for _cmd in _cmd_list:
            self.debug_stream("Custom command : %s" % _cmd[0])
            argout.append( json.dumps(_cmd))

        return argout

    @command(dtype_out=[str], doc_out='list of axis custom attributes')
    def GetCustomAttributeList(self):
        """
        Returns the list of custom attributes.
        JSON format.
        """
        base_attrs = BlissAxis.TangoClassClass.attr_list
        attrs = self.get_device_class().attr_list
        custom_attr_names = set(attrs).difference(base_attrs)

        argout = list()

        for custom_attr_name in custom_attr_names:
            custom_attr = attrs[custom_attr_name][0]
            type_str = types_conv_tab_inv[custom_attr[0]]
            access_str = access_conv_tab_inv[custom_attr[2]]
            attr_item = custom_attr_name, type_str, access_str
            argout.append(json.dumps(attr_item))

        return argout

    @command(dtype_out=str, doc_out='name of the class of the controller of this axis')
    def GetControllerClassName(self):
        """
        Returns the name of the class of the controller.
        ex: 'Mockup'
        """
        argout = self.axis.controller.get_class_name()
        return argout

    @command
    def SettingsToConfig(self):
        """
        Saves settings in configuration file (YML or XML)
        """
        self.axis.settings_to_config()

    @command(dtype_in=bool,
             doc_in='reload (true to do a reload before apply configuration, false not to)')
    def ApplyConfig(self, reload):
        """
        Reloads configuration and apply it.
        """
        self.axis.apply_config(reload=reload)

    @command(dtype_in=float, doc_in='new user position (=dial*sign+offset)',
             dtype_out=float, doc_out='previous user position')
    def SetPosition(self, new_user_pos):
        """
        (Re)Set the user position (no motor move): just change offset
        """
        old_user = self.axis.position()
        self.axis.position(new_user_pos)
        return old_user

    @command(dtype_in=float, doc_in='new dial position (=(user-offset)/sign)',
             dtype_out=float, doc_out='previous dial position')
    def SetDial(self, new_dial_pos):
        """
        (Re)Set the dial position (no motor move): write into controller
        The offset is kept constant, so the user position also changes
        """
        old_dial = self.axis.dial()
        self.axis.dial(new_dial_pos)
        return old_dial

def get_server_axis_names(instance_name=None):
    if instance_name is None:
        _, instance_name, _ = get_server_info()

    cfg = bliss_config.beacon_get_config()
    result = []
    for item_name in cfg.names_list:
        item_cfg = cfg.get_config(item_name)
        if item_cfg.plugin == 'emotion' and \
                instance_name in item_cfg.get('tango_server', ()):
            result.append(item_name)
    return result


def get_server_info(argv=None):
    if argv is None:
        argv = sys.argv

    file_name = os.path.basename(argv[0])
    server_name = os.path.splitext(file_name)[0]
    instance_name = argv[1]
    server_instance = '/'.join((server_name, instance_name))
    return server_name, instance_name, server_instance


def register_server(db=None):
    if db is None:
        db = PyTango.Database()

    server_name, instance_name, server_instance = get_server_info()

    domain = os.environ.get('BEAMLINENAME', 'bliss')
    dev_name = '{0}/BlissAxisManager/{1}'.format(domain, instance_name)
    elog.info(" registering new server: %s" % dev_name)
    info = PyTango.DbDevInfo()
    info.server = server_instance
    info._class = 'BlissAxisManager'
    info.name = dev_name
    db.add_device(info)


def get_devices_from_server(argv=None, db=None):
    if db is None:
        db = PyTango.Database()

    if argv is None:
        argv = sys.argv

    # get sub devices
    _, _, personalName = get_server_info(argv)
    result = list(db.get_device_class_list(personalName))

    # dict<dev_name: tango_class_name>
    dev_dict = dict(zip(result[::2], result[1::2]))

    class_dict = {}
    for dev, class_name in dev_dict.items():
        devs = class_dict.setdefault(class_name, [])
        devs.append(dev)

    class_dict.pop('DServer', None)

    return class_dict


def initialize_logging(argv):
    try:
        log_param = [param for param in argv if "-v" in param]
        if log_param:
            log_param = log_param[0]
            # print "-vN log flag found   len=%d" % len(log_param)
            if len(log_param) > 2:
                tango_log_level = int(log_param[2:])
            elif len(log_param) > 1:
                tango_log_level = 4
            else:
                print "BlissAxisManager.py - ERROR LOG LEVEL"

            if tango_log_level == 1:
                elog.level(40)
            elif tango_log_level == 2:
                elog.level(30)
            elif tango_log_level == 3:
                elog.level(20)
            else:
                elog.level(10)
        else:
            # by default : show INFO
            elog.level(20)
            tango_log_level = 0
    except PyTango.DevFailed:
        print traceback.format_exc()
        elog.exception("Error in initializing logging")
        sys.exit(0)


def __recreate(db=None, new_server=False):

    if db is None:
        db = PyTango.Database()

    server_name, server_instance, server_name = get_server_info()
    registered_servers = set(db.get_instance_name_list('BlissAxisManager'))

    # check if server exists in database. If not, create it.
    if server_instance not in registered_servers:
        if new_server:
            register_server(db=db)
        else:
            print "The device server %s is not defined in database. " \
                  "Exiting!" % server_name
            print "hint: start with '-n' to create a new one automatically"
            sys.exit(255)

    dev_map = get_devices_from_server(db=db)

    # if in a jive wizard workflow, return no axis
    if not dev_map.get('BlissAxisManager', ()):
        return ()

    axis_names = get_server_axis_names()

    # gather info about current axes registered in database and
    # new axis from config

    manager_dev_name = dev_map['BlissAxisManager'][0]

    if db.get_device_property(manager_dev_name, "config_file")["config_file"]:
        elog.error('Use of XML configuration not supported anymore. '
                   'Turn to beacon', raise_exception=False)
        sys.exit(-1)

    if db.get_device_property(manager_dev_name, "axes")["axes"]:
        elog.error('Use of \'axes\' property not supported anymore',
                   raise_exception=False)
        elog.error('Configure by adding: \'tango_server: %s\' in each '
                   'axis yaml instead' % server_instance,
                   raise_exception=False)
        sys.exit(-1)

    return __recreate_axes(server_name, manager_dev_name,
                           axis_names, dev_map, db=db)


def __recreate_axes(server_name, manager_dev_name, axis_names,
                    dev_map, db=None):
    db = db or PyTango.Database()

    curr_axes = {}
    for dev_class, dev_names in dev_map.items():
        if not dev_class.startswith('BlissAxis_'):
            continue
        for dev_name in dev_names:
            curr_axis_name = dev_name.rsplit("/", 1)[-1]
            try:
                bliss.get_axis(curr_axis_name)
            except:
                elog.info("Error instantiating %s (%s): skipping!!" % (curr_axis_name, dev_name))
                traceback.print_exc()
                continue
            curr_axes[curr_axis_name] = dev_name, dev_class

    axis_names_set = set(axis_names)
    curr_axis_names_set = set(curr_axes)
    new_axis_names = axis_names_set.difference(curr_axis_names_set)
    old_axis_names = curr_axis_names_set.difference(axis_names_set)

    domain, family, member = manager_dev_name.split('/', 2)

    # remove old axes
    for axis_name in old_axis_names:
        dev_name, klass_name = curr_axes[axis_name]
        elog.debug('removing old axis %s (%s)' % (dev_name, axis_name))
        db.delete_device(dev_name)

    # add new axes
    for axis_name in new_axis_names:
        dev_name = "%s/%s_%s/%s" % (domain, family, member, axis_name)
        info = PyTango.DbDevInfo()
        info.server = server_name
        info._class = 'BlissAxis_' + axis_name
        info.name = dev_name
        elog.debug('adding new axis %s (%s)' % (dev_name, axis_name))
        db.add_device(info)
        # try to create alias if it doesn't exist yet
        try:
            db.get_device_alias(axis_name)
        except PyTango.DevFailed:
            elog.debug('registering alias for %s (%s)' % (dev_name, axis_name))
            db.put_device_alias(dev_name, axis_name)
 
    axes, tango_classes = [], []
    for axis_name in curr_axis_names_set:
        axis = bliss.get_axis(axis_name)
        axes.append(axis)
        tango_class = __create_tango_axis_class(axis)
        tango_classes.append(tango_class)

    return axes, tango_classes


# callback from the Bliss server
def initialize_bliss(info, db=None):
    shell_info = info['shell_info']
    session_cfg = shell_info[-1]
    object_names = session_cfg['config_objects']
    server_type  = info['server_type']
    server_instance = info['server_instance']
    server_name = server_type + '/' + server_instance

    cfg = bliss_config.beacon_get_config()

    axis_names = []
    for name in object_names:
        obj_cfg = cfg.get_config(name)
        if obj_cfg.plugin == 'emotion':
            axis_names.append(name)

    axes, classes = __recreate_axes(server_name, info['manager_device_name'],
                                    axis_names, info['device_map'], db=db)
    return classes


def __create_tango_axis_class(axis):
    BlissAxisClass = BlissAxis.TangoClassClass
    new_axis_class_class = types.ClassType("BlissAxisClass_%s" % axis.name, (BlissAxisClass,), {})
    new_axis_class = types.ClassType("BlissAxis_%s" % axis.name, (BlissAxis,), {})
    new_axis_class.TangoClassName = "BlissAxis_%s" % axis.name
    new_axis_class.TangoClassClass = new_axis_class_class

    new_axis_class_class.attr_list = dict(BlissAxisClass.attr_list)
    new_axis_class_class.cmd_list = dict(BlissAxisClass.cmd_list)

    """
    CUSTOM COMMANDS
    """
    # Search and adds custom commands.
    _cmd_list = axis.custom_methods_list
    elog.debug("'%s' custom commands:" % axis.name)
    elog.debug(', '.join(map(str, _cmd_list)))

    def create_cmd(cmd_name):
        def cmd(self, *args, **kwargs):
            method = getattr(self.axis, cmd_name)
            return get_worker().execute(method, *args, **kwargs)
        return cmd

    _attr_list = axis.custom_attributes_list

    for (fname, (t1, t2)) in _cmd_list:
        # Skip the attr set/get methods
        attr = [n for n, t, a in _attr_list
                if fname in ['set_%s' % n, 'get_%s' % n]]
        if attr:
            continue

        setattr(new_axis_class, fname, create_cmd(fname))

        tin = types_conv_tab[t1]
        tout = types_conv_tab[t2]

        new_axis_class_class.cmd_list.update({fname: [[tin, ""], [tout, ""]]})

        elog.debug("   %s (in: %s, %s) (out: %s, %s)" % (fname, t1, tin, t2, tout))

    # CUSTOM ATTRIBUTES
    elog.debug("'%s' custom attributes:" % axis.name)
    elog.debug(', '.join(map(str, _attr_list)))

    for name, t, access in _attr_list:
        attr_info = [types_conv_tab[t],
                     PyTango.AttrDataFormat.SCALAR]
        if 'r' in access:
            def read(self, attr):
                method = getattr(self.axis, "get_" + attr.get_name())
                value = get_worker().execute(method)
                attr.set_value(value)
            setattr(new_axis_class, "read_%s" % name, read)
        if 'w' in access:
            def write(self, attr):
                method = getattr(self.axis, "set_" + attr.get_name())
                value = attr.get_write_value()
                method(value)
            setattr(new_axis_class, "write_%s" % name, write)

        write_dict = {'r': 'READ', 'w': 'WRITE', 'rw': 'READ_WRITE'}
        attr_write = getattr(PyTango.AttrWriteType, write_dict[access])
        attr_info.append(attr_write)
        new_axis_class_class.attr_list[name] = [attr_info]

    """
    CUSTOM SETTINGS AS ATTRIBUTES.
    """
    elog.debug(" BlissAxisManager.py : %s : -------------- SETTINGS -----------------" % axis.name)

    for setting_name in axis.settings:
        if setting_name in ["velocity", "position", "dial_position", "state",
                            "offset", "low_limit", "high_limit", "acceleration", "_set_position"]:
            elog.debug(" BlissAxisManager.py -- std SETTING %s " % (setting_name))
        else:
            _setting_type = axis.controller.axis_settings.convert_funcs[setting_name]
            _attr_type = types_conv_tab[_setting_type]
            elog.debug(" BlissAxisManager.py -- adds SETTING %s as %s attribute" % (setting_name, _attr_type))

            # Updates Attributes list.
            new_axis_class_class.attr_list.update({setting_name:
                                                   [[_attr_type,
                                                     PyTango.AttrDataFormat.SCALAR,
                                                      PyTango.AttrWriteType.READ_WRITE], {
                'Display level': PyTango.DispLevel.OPERATOR,
                'format': '%10.3f',
                'description': '%s : u 2' % setting_name,
                'unit': 'user units/s^2',
                'label': setting_name,
                }]})

            # Creates functions to read and write settings.
            def read_custattr(self, attr):
                value = get_worker().execute(self.axis.get_setting,
                                             attr.get_name())
                attr.set_value(value)
            setattr(new_axis_class, "read_%s" % setting_name, read_custattr)

            def write_custattr(self, attr):
                get_worker().execute(self.axis.set_setting, attr.get_name(),
                                     attr.get_write_value())
            setattr(new_axis_class, "write_%s" % setting_name, write_custattr)

    return new_axis_class


def main(argv=None):
    start_time = time.time()

    if argv is None:
        argv = sys.argv
    argv = list(argv)

    try:
        argv.remove('-n')
        new_server = True
    except ValueError:
        new_server = False

    try:
        # initialize logging as soon as possible
        initialize_logging(argv)

        bliss_config.set_backend('beacon')

        # if querying list of instances, just return
        if len(argv) < 2 or argv[1] == '-?':
            util = PyTango.Util(argv)
            # no need since tango exits the process when it finds '-?'
            # (tango is not actually a library :-)
            return

        axes, axes_classes = __recreate(new_server=new_server)
        del axes

        util = PyTango.Util(argv)
        db = util.get_database()

    except PyTango.DevFailed:
        print traceback.format_exc()
        elog.exception(
            "Error in server initialization")
        sys.exit(0)

    klasses = [BlissAxisManager] + axes_classes

    dt = time.time() - start_time
    elog.info('server configured (took %6.3fs)' % dt)

    from PyTango import GreenMode
    from PyTango.server import run
    run(klasses, green_mode=GreenMode.Gevent)


if __name__ == '__main__':
    main()
