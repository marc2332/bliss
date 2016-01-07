#!/usr/bin/env python
# -*- coding:utf-8 -*-
import bliss
import bliss.config.motors as bliss_config
import bliss.common.log as elog

import PyTango
import TgGevent

import os
import sys
import time
import traceback
import types
import json

try:
    from bliss.config.conductor.connection import ConnectionException
except:
    print "beacon not installed ?"

    class ConnectionException(Exception):
        pass

class bcolors:
    PINK = '\033[95m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    ENDC = '\033[0m'


class BlissAxisManager(PyTango.Device_4Impl):
    axis_dev_list = None
    axis_dev_names = None

    def __init__(self, cl, name):
        PyTango.Device_4Impl.__init__(self, cl, name)
        self.debug_stream("In __init__() of controller")
        self.init_device()


    def delete_device(self):
        self.debug_stream("In delete_device() of controller")

    def init_device(self):
        self.debug_stream("In init_device() of controller")
        self.get_device_properties(self.get_device_class())


    def dev_state(self):
        """ This command gets the device state (stored in its device_state
        data member) and returns it to the caller.

        :param : none
        :type: PyTango.DevVoid
        :return: Device state
        :rtype: PyTango.CmdArgType.DevState """
#        self.debug_stream("In BlissAxisManager dev_state()")
        argout = PyTango.DevState.UNKNOWN

        U = PyTango.Util.instance()
        dev_list = U.get_device_list("*")
        # [BlissAxisManager(id26/bliss/cyrtest),
        # BlissAxis_robd(id26/bliss_cyrtest/robd),
        # BlissAxis_robc(id26/bliss_cyrtest/robc),
        # BlissAxis_robb(id26/bliss_cyrtest/robb),
        # BlissAxis_roba(id26/bliss_cyrtest/roba),
        # DServer(dserver/BlissAxisManager/cyrtest)]

        # Creates the list of BlissAxis devices.
        if self.axis_dev_list is None:
            self.axis_dev_list = list()
            for dev in dev_list:
                dev_name = dev.get_name()
                if "bliss_" in dev_name:
                    self.axis_dev_list.append(dev)

        # Builds the BlissAxisManager State from states of BlissAxis devices.
        _bliss_working = True
        _bliss_moving = False
        for dev in self.axis_dev_list:
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
        for dev in self.axis_dev_list:
            E_status = E_status + dev.get_name() + ":" + dev.get_state().name + ";" + dev.get_status() + "\n"
        self.set_status(E_status)

        return self.get_state()


    def GetAxisList(self):
        """
        Returns the list of BlissAxisManager axes of this device.
        """
        argout = list()

        U = PyTango.Util.instance()
        dev_list = U.get_device_list("*")
        # Creates the list of BlissAxis devices names.
        if self.axis_dev_names is None:
            self.axis_dev_names = list()
            for dev in dev_list:
                dev_name = dev.get_name()
                if "bliss_" in dev_name:
                    self.axis_dev_names.append(dev_name)

        print "axes list : ", self.axis_dev_names

        for _axis in self.axis_dev_names:
            argout.append(_axis)
        return argout

class BlissAxisManagerClass(PyTango.DeviceClass):

    #    Class Properties
    class_property_list = {
    }

    #    Device Properties
    device_property_list = {
        'config_file':
        [PyTango.DevString,
         "( Deprecated ? ) Path to the XML configuration file\n  ---->XML only \n --->let empty if you want to use Beacon) ",
        [["/users/blissadm/local/userconf/bliss/XXX.xml"]]],
        'axes':
        [PyTango.DevString,
         "List of axes to instanciate \n ---> BEACON only \n let empty to use XML config file (only if you know what you are doing...).",
         [["mot1 mot2 mot3"]]],
    }

    #    Command definitions
    cmd_list = {
        'GetAxisList':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVarStringArray, "List of axis"]]
    }

# Device States Description
# ON : The motor powered on and is ready to move.
# MOVING : The motor is moving
# FAULT : The motor indicates a fault.
# ALARM : The motor indicates an alarm state for example has reached
# a limit switch.
# OFF : The power on the moror drive is switched off.
# DISABLE : The motor is in slave mode and disabled for normal use
class BlissAxis(PyTango.Device_4Impl):

    def __init__(self, cl, name):
        PyTango.Device_4Impl.__init__(self, cl, name)

        self._axis_name = name.split('/')[-1]
        self._ds_name = name
        self.debug_stream("In __init__() of axis")
        try:
            self.init_device()
        except:
            self.fatal_stream("CANNOT INIT DEVICE FOR AXIS")

    def delete_device(self):
        self.debug_stream("In delete_device() of axis")

    def init_device(self):
        self.debug_stream("In init_device() of axis")
        self.get_device_properties(self.get_device_class())

        # -v1
        self.info_stream("INFO STREAM ON ++++++++++++++++++++++++++")
        self.warn_stream("WARN STREAM ON ++++++++++++++++++++++++++")
        self.error_stream("ERROR STREAM ON ++++++++++++++++++++++++++")
        self.fatal_stream("FATAL STREAM ON ++++++++++++++++++++++++++")

        # -v3 (-v == -v4)
        self.debug_stream("DEBUG STREAM ON ++++++++++++++++++++++++++")

        try:
            self.axis = TgGevent.get_proxy(bliss.get_axis, self._axis_name)
            self.kontroler = TgGevent.get_proxy(self.axis.controller)
        except:
            elog.error("unable to get kontroller or axis")
            self.set_status(traceback.format_exc())

        self.debug_stream("axis found : %s" % self._axis_name)

        self.once = False

        self._init_time = time.time()
        self._t = time.time()

        self.attr_Home_position_read = 0.0
        self.attr_StepSize_read = 0.0
        self.attr_Steps_per_unit_read = 0.0
        self.attr_Acceleration_read = 1.0
        self.attr_HardLimitLow_read = False
        self.attr_HardLimitHigh_read = False
        self.attr_Backlash_read = 0.0
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
        self.dev_state()

        # elog.info("    %s" % self.axis.get_info())
        elog.info(" BlissAxisManager.py Axis " + bcolors.PINK + self._ds_name + bcolors.ENDC + " initialized")

    def always_executed_hook(self):

        # here instead of in init_device due to (Py?)Tango bug :
        # device does not really exist in init_device... (Cyril)
        if not self.once:
            try:
                # Initialises "set values" of attributes.
                # Position
                attr = self.get_device_attr().get_attr_by_name("Position")
                attr.set_write_value(self.axis.position())

                # Velocity
                attr = self.get_device_attr().get_attr_by_name("Velocity")
                attr.set_write_value(self.axis.velocity())
            except:
                elog.info(
                    "Cannot set one of the attributes write value")
            finally:
                self.once = True


    def dev_state(self):
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
            PyTango.Device_4Impl.dev_state(self)

        # print "dev_state %s" % self.get_state()
        return self.get_state()

    def dev_status(self):
        # update current state AND status
        self.dev_state()

        # get the updated status as a string
        self._status = self.get_status()
        return self._status

    def read_Steps_per_unit(self, attr):
        self.debug_stream("In read_Steps_per_unit()")
        attr.set_value(self.axis.steps_per_unit())

    def write_Steps_per_unit(self, attr):
        self.debug_stream("In write_Steps_per_unit()")
        # data = attr.get_write_value()
        elog.debug("Not implemented")

    def read_Steps(self, attr):
        self.debug_stream("In read_Steps()")
        _spu = float(self.axis.steps_per_unit())
        _steps = _spu * self.axis.position()
        attr.set_value(int(round(_steps)))

#    def write_Steps(self, attr):
#        self.debug_stream("In write_Steps()")
#        data=attr.get_write_value()

    def read_Position(self, attr):
        self.debug_stream("In read_Position()")
        if self.axis.is_moving():
            quality = PyTango.AttrQuality.ATTR_CHANGING
        else:
            quality = PyTango.AttrQuality.ATTR_VALID
        _t = time.time()

        _pos = self.axis.position()

        # updates value of "position" attribute.
        attr.set_value(_pos)

        _duration = time.time() - _t
        if _duration > 0.05:
            print "BlissAxisManager.py : {%s} read_Position : duration seems too long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)

    def write_Position(self, attr):
        """
        Sends movement command to BlissAxisManager axis.
        NB : take care to call WaitMove before sending another movement
        self.write_position_wait is a device property (False by default).
        """
        self.debug_stream("In write_Position()")
        # self.axis.move(attr.get_write_value(), wait=False)
        # self.axis.move(attr.get_write_value(), wait=True)

        self.set_state(PyTango.DevState.MOVING)
        self.axis.move(attr.get_write_value(), wait=self.write_position_wait)
        self.set_state(PyTango.DevState.ON)

    def is_Position_allowed(self, req_type):
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

    def read_Measured_Position(self, attr):
        self.debug_stream("In read_Measured_Position()")
        _t = time.time()
        attr.set_value(self.axis.measured_position())
        _duration = time.time() - _t

        if _duration > 0.01:
            print "BlissAxisManager.py : {%s} read_Measured_Position : duration seems long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)

    def read_Acceleration(self, attr):
        _acc = self.axis.acceleration()
        self.debug_stream("In read_Acceleration(%f)" % float(_acc))
        attr.set_value(_acc)


    def write_Acceleration(self, attr):
        data = float(attr.get_write_value())
        self.debug_stream("In write_Acceleration(%f)" % data)
        self.axis.acceleration(data)

    def read_AccTime(self, attr):
        self.debug_stream("In read_AccTime()")
        _acc_time = self.axis.acctime()
        self.debug_stream("In read_AccTime(%f)" % float(_acc_time))
        attr.set_value(_acc_time)

    def write_AccTime(self, attr):
        data = float(attr.get_write_value())
        self.axis.acctime(data)
        self.debug_stream("In write_AccTime(%f)" % float(data))

    def read_Velocity(self, attr):
        _vel = self.axis.velocity()
        attr.set_value(_vel)
        self.debug_stream("In read_Velocity(%g)" % _vel)

    def write_Velocity(self, attr):
        data = float(attr.get_write_value())
        self.debug_stream("In write_Velocity(%g)" % data)
        self.axis.velocity(data)

    def read_Backlash(self, attr):
        self.debug_stream("In read_Backlash()")
        self.attr_Backlash_read = self.axis.backlash()
        attr.set_value(self.attr_Backlash_read)

#    def write_Backlash(self, attr):
#        self.debug_stream("In write_Backlash()")
#        data = attr.get_write_value()
#        self.debug_stream("write backlash %s" % data)

    def read_Offset(self, attr):
        self.debug_stream("In read_Offset()")
        self.attr_Offset_read = self.axis.offset()
        attr.set_value(self.attr_Offset_read)

#    def write_Offset(self, attr):
#        self.debug_stream("In write_Offset()")
#        data = attr.get_write_value()
#        self.debug_stream("write offset %s" % data)
#        self.axis.offset(data)

    def read_Tolerance(self, attr):
        self.debug_stream("In read_Tolerance()")
        self.attr_Tolerance_read = self.axis.tolerance()
        attr.set_value(self.attr_Tolerance_read)

    def write_Tolerance(self, attr):
        self.debug_stream("In write_Tolerance()")
        data = attr.get_write_value()
        self.debug_stream("write tolerance %s" % data)

    def read_Home_position(self, attr):
        self.debug_stream("In read_Home_position()")
        attr.set_value(self.attr_Home_position_read)

    def write_Home_position(self, attr):
        self.debug_stream("In write_Home_position()")
        data = float(attr.get_write_value())
        self.attr_Home_position_read = data

    def read_HardLimitLow(self, attr):
        self.debug_stream("In read_HardLimitLow()")
        # Update state and return cached value.
        self.dev_state()
        attr.set_value(self.attr_HardLimitLow_read)

    def read_HardLimitHigh(self, attr):
        self.debug_stream("In read_HardLimitHigh()")
        # Update state and return cached value.
        self.dev_state()
        attr.set_value(self.attr_HardLimitHigh_read)

    def read_PresetPosition(self, attr):
        self.debug_stream("In read_PresetPosition()")
        attr.set_value(self.attr_PresetPosition_read)

    def write_PresetPosition(self, attr):
        data = float(attr.get_write_value())
        self.debug_stream("In write_PresetPosition(%g)" % data)
        self.attr_PresetPosition_read = data
        # NOTE MP: if using TANGO DS let's consider that there is
        # a smart client out there who is handling the user/offset.
        # Therefore don't the user position/offset of EMotion.
        # Which means: always keep dial position == user position
        self.axis.dial(data)
        self.axis.position(data)

    def read_FirstVelocity(self, attr):
        self.debug_stream("In read_FirstVelocity()")
        attr.set_value(self.attr_FirstVelocity_read)
        #attr.set_value(self.axis.FirstVelocity())

    def write_FirstVelocity(self, attr):
        self.debug_stream("In write_FirstVelocity()")
        data = attr.get_write_value()
        self.attr_FirstVelocity_read = data
        # self.axis.FirstVelocity(data)

    def read_Home_side(self, attr):
        self.debug_stream("In read_Home_side()")
        attr.set_value(self.attr_Home_side_read)

    def read_StepSize(self, attr):
        self.debug_stream("In read_StepSize()")
        attr.set_value(self.attr_StepSize_read)

    def write_StepSize(self, attr):
        self.debug_stream("In write_StepSize()")
        data = attr.get_write_value()
        self.attr_StepSize_read = data
        attr.set_value(data)

    def read_attr_hardware(self, data):
        pass
        # self.debug_stream("In read_attr_hardware()")

    def read_trajpar(self, attr):
        self.debug_stream("In read_trajpar()")
        attr.set_value(self.attr_trajpar_read)

    def write_trajpar(self, attr):
        self.debug_stream("In write_trajpar()")
        data = attr.get_write_value()

    """
    Motor command methods
    """
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

    def GoHome(self):
        """ 
        Moves the motor to the home position given by a home switch.
        Searches home switch in POSITIVE direction.
        """
        self.debug_stream("In GoHome()")
        self.axis.home(switch=1, wait=False)

    def GoHomeInversed(self):
        """
        Moves the motor to the home position given by a home switch.
        Searches home switch in NEGATIVE direction.
        """
        self.debug_stream("In GoHomeInversed()")
        self.axis.home(switch=-1, wait=False)

    def Abort(self):
        """ Stop immediately the motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Abort()")
        self.axis.stop()

    def Stop(self):
        """ Stop gently the motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Stop()")
        self.axis.stop()

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

    def GetInfo(self):
        """ provide information about the axis.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevString """
        self.debug_stream("In GetInfo()")
        return self.axis.get_info()

    def RawWrite(self, argin):
        """ Sends a raw command to the axis. Be carefull!

        :param argin: String with command
        :type: PyTango.DevString
        :return: None
        """
        self.debug_stream("In RawWrite()")

        return self.kontroler.raw_write(argin)

    def RawWriteRead(self, argin):
        """ Sends a raw command to the axis and read the result.
        Be carefull!

        :param argin: String with command
        :type: PyTango.DevString
        :return: answer from controller.
        :rtype: PyTango.DevString """
        self.debug_stream("In RawWriteRead()")

        return self.kontroler.raw_write_read(argin)

    def CtrlPosition(self):
        """ Returns raw axis position read by controller.

        :param argin: None
        :type: PyTango.DevVoid
        :return: answer from controller.
        :rtype: PyTango.DevFloat """
        self.debug_stream("In CtrlPosition()")

        return self.axis.read_position()

    def SyncHard(self):
        self.debug_stream("In SyncHard()")
        return self.axis.sync_hard()

    def WaitMove(self):
        """ Waits end of last motion

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In WaitMove()")
        return self.axis.wait_move()

    def ReadConfig(self, argin):
        return self.axis.config().get(argin)

    def SetGate(self, argin):
        """
        Activate or de-activate gate of this axis.
        """
        self.debug_stream("In SetGate(%s)" % argin)

        return self.axis.set_gate(argin)

    def GetCustomCommandList(self):
        """
        Returns the list of custom commands.
        JSON format.
        """
        _cmd_list = self.axis.custom_methods_list()

        argout = list()

        for _cmd in _cmd_list:
            self.debug_stream("Custom command : %s" % _cmd)
            argout.append( json.dumps(_cmd))

        return argout


    def SettingsToConfig(self):
        """
        Saves settings in configuration file (YML or XML)
        """
        self.axis.settings_to_config()

    def ApplyConfig(self):
        """
        Reloads configuration and apply it.
        """
        self.axis.apply_config()


class BlissAxisClass(PyTango.DeviceClass):
    #    Class Properties
    class_property_list = {
    }

    #    Device Properties
    device_property_list = {
        'write_position_wait':
        [PyTango.DevBoolean,
         "Write position waits for end of motion",
         False],
    }

    #    Command definitions
    cmd_list = {
        'On':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'Off':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'GoHome':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'Abort':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'Stop':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'StepUp':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"], {'Display level': PyTango.DispLevel.EXPERT, }],
        'StepDown':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"], {'Display level': PyTango.DispLevel.EXPERT, }],
        'GetInfo':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevString, "Info string returned by the axis"]],
        'RawWrite':
        [[PyTango.DevString, "Raw command to be send to the axis. Be carefull!"],
         [PyTango.DevVoid, "No answer"],
         {'Display level': PyTango.DispLevel.EXPERT, }],
        'RawWriteRead':
        [[PyTango.DevString, "Raw command to be send to the axis. Be carefull!"],
         [PyTango.DevString, "Answer returned by the controller"],
         {'Display level': PyTango.DispLevel.EXPERT, }],
        'CtrlPosition':
        [[PyTango.DevVoid, ""],
         [PyTango.DevFloat, "Controller raw position (used to manage discrepency)"],
         {'Display level': PyTango.DispLevel.EXPERT, }],
        'SyncHard':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'WaitMove':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
        'ReadConfig':
        [[PyTango.DevString, "Parameter name"],
         [PyTango.DevString, "Configuration value"]],
        'SetGate':
        [[PyTango.DevLong, "state of the gate 0/1"],
         [PyTango.DevVoid, ""]],
        'GetCustomCommandList':
        [[PyTango.DevVoid, ""],
         [PyTango.DevVarStringArray, "List of axis custom commands"]],
        'ApplyConfig':
        [[PyTango.DevVoid, ""],
         [PyTango.DevVoid, "calls apply_config ???"]],
        'SettingsToConfig':
        [[PyTango.DevVoid, ""],
         [PyTango.DevVoid, "calls settings_to_config ???"]]
    }

    #    Attribute definitions
    attr_list = {
        'Steps_per_unit':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Steps per user unit",
             'unit': "steps/uu",
             'format': "%7.1f",
             # 'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Steps':
        [[PyTango.DevLong,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Steps",
             'unit': "steps",
             'format': "%6d",
             'description': "number of steps in the step counter\n",
        }],
        'Position':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Position",
             'unit': "uu",
             'format': "%10.3f",
             'description': "The desired motor position in user units.",
        }],
        'Measured_Position':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Measured position",
             'unit': "uu",
             'format': "%10.3f",
             'description': "The measured motor position in user units.",
        }],
        'Acceleration':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Acceleration",
             'unit': "user units/s^2",
             'format': "%10.3f",
             'description': "Acceleration of the motor in uu/s2",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'AccTime':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Acceleration Time",
             'unit': "s",
             'format': "%10.6f",
             'description': "The acceleration time of the motor (in seconds).",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Velocity':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Velocity",
             'unit': "units/s",
             'format': "%10.3f",
             'description': "The constant velocity of the motor.",
             #                'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Backlash':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Backlash",
             'unit': "uu",
             'format': "%5.3f",
             'description': "Backlash to be applied to each motor movement",
             #'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Offset':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Offset",
             'unit': "uu",
             'format': "%7.5f",
             'description': "Offset between dial and user",
             #'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Tolerance':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "Tolerance",
             'unit': "uu",
             'format': "%7.5f",
             'description': "Tolerance between dial and user",
             #'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Home_position':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Home position",
             'unit': "uu",
             'format': "%7.3f",
             'description': "Position of the home switch",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'HardLimitLow':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "low limit switch state",
        }],
        'HardLimitHigh':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'label': "up limit switch state",
        }],
        'PresetPosition':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "Preset Position",
             'unit': "uu",
             'format': "%10.3f",
             'description': "preset the position in the step counter",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'FirstVelocity':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'label': "first step velocity",
             'unit': "units/s",
             'format': "%10.3f",
             'description': "number of unit/s for the first step and for \
             the move reference",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'Home_side':
        [[PyTango.DevBoolean,
          PyTango.SCALAR,
          PyTango.READ],
         {
             'description': "indicates if the axis is below or above \
             the position of the home switch",
        }],
        'StepSize':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE],
         {
             'unit': "uu",
             'format': "%10.3f",
             'description': "Size of the relative step performed by the \
             StepUp and StepDown commands.\nThe StepSize\
             is expressed in physical unit.",
             'Display level': PyTango.DispLevel.EXPERT,
        }],
        'trajpar':
        [[PyTango.DevFloat,
          PyTango.IMAGE,
          PyTango.READ_WRITE, 1000, 5]],
    }


def get_devices_from_server():
    # get sub devices
    fullpathExecName = sys.argv[0]
    execName = os.path.split(fullpathExecName)[-1]
    execName = os.path.splitext(execName)[0]
    personalName = '/'.join([execName, sys.argv[1]])
    db = PyTango.Database()
    result = db.get_device_class_list(personalName)

    # "result" is :  DbDatum[
    #    name = 'server'
    # value_string = ['dserver/BlissAxisManager/cyril', 'DServer',
    # 'pel/bliss/00', 'Bliss', 'pel/bliss_00/fd', 'BlissAxis']]
    # print "--------------------"
    # print result
    # print "++++++++++++++++++++"
    class_dict = {}

    for i in range(len(result.value_string) / 2):
        deviceName = result.value_string[i * 2]
        class_name = result.value_string[i * 2 + 1]
        if class_name not in class_dict:
            class_dict[class_name] = []

        class_dict[class_name].append(deviceName)

    return class_dict


def delete_bliss_axes():
    """
    Removes BlissAxisManager axis devices from the database.
    """
    db = PyTango.Database()

    bliss_axis_device_names = get_devices_from_server().get('BlissAxis')

    for _axis_device_name in bliss_axis_device_names:
        elog.info("Deleting existing BlissAxisManager axis: %s" %
                  _axis_device_name)
        db.delete_device(_axis_device_name)


def delete_unused_bliss_axes():
    """
    Removes BlissAxisManager axes that are not running.
    """
    # get BlissAxis (only from current instance).
    bliss_axis_device_names = get_devices_from_server().get('BlissAxis')
    elog.info("Axes: %r" % bliss_axis_device_names)


def main():
    try:
        delete_unused_bliss_axes()
    except:
        elog.error(
            "Cannot delete unused bliss axes.",
            raise_exception=False)

    try:
        py = PyTango.Util(sys.argv)

        log_param = [param for param in sys.argv if "-v" in param]
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

        print ""

        # elog.info("tango log level=%d" % tango_log_level)
        # elog.debug("BlissAxisManager.py debug message")
        # elog.error("BlissAxisManager.py error message", raise_exception=False)

        # Searches for bliss devices defined in tango database.
        U = PyTango.Util.instance()
        db = U.get_database()
        device_list = get_devices_from_server().get('BlissAxisManager')

        if device_list is not None:
            _device = device_list[0]
            elog.info(" BlissAxisManager.py - BlissAxisManager device : %s" % _device)
            try:
                _config_file = db.get_device_property(_device, "config_file")["config_file"][0]
            except:
                elog.info(" BlissAxisManager.py - 'config_file' property not present ?")
                _config_file = None

            first_run = False
        else:
            elog.error("[FIRST RUN] New server never started ? -> no database entry...", raise_exception=False)
            elog.error("[FIRST RUN] NO CUSTOM COMANDS :( ", raise_exception=False)
            elog.error("[FIRST RUN] Restart DS to havec CUSTOM COMMANDS", raise_exception=False)
            first_run = True

        py.add_class(BlissAxisManagerClass, BlissAxisManager)
        # py.add_class(BlissAxisClass, BlissAxis)

        if not first_run:
            if _config_file is not None:
                elog.info(" BlissAxisManager.py - config file : " + bcolors.PINK + _config_file + bcolors.ENDC)
                try:
                    TgGevent.execute(bliss.load_cfg, _config_file)
                except:
                    elog.error("error (not present or syntax error?) in reading config file : %s" %
                               _config_file, raise_exception=False)
                    sys.excepthook(*sys.exc_info())
                    sys.exit(-1)
                else:
                    # Get axis names defined in config file.
                    axis_names = bliss_config.axis_names_list()
            else:
                elog.info(" BlissAxisManager.py - " + bcolors.PINK + "beacon config" + bcolors.ENDC)
                # Get axes names from property (= use beacon to get axis objects)
                bliss_config.BACKEND = "beacon"
                axis_names = db.get_device_property(_device, "axes")["axes"][0].split()

            elog.debug("axis names list : %s" % axis_names)

            for axis_name in axis_names:
                elog.debug("BlissAxisManager.py : _____________ axis %s _____________" % axis_name)
                try:
                    _axis = TgGevent.get_proxy(bliss.get_axis, axis_name)
                except ConnectionException:
                    elog.error("beacon_server seems not running")
                    sys.exit(-1)
                except:
                    print traceback.format_exc()
                    sys.exit(-1)

                new_axis_class_class = types.ClassType("BlissAxisClass_%s" % axis_name, (BlissAxisClass,), {})
                new_axis_class = types.ClassType("BlissAxis_%s" % axis_name, (BlissAxis,), {})

                types_conv_tab = {
                    None: PyTango.DevVoid,
                    str: PyTango.DevString,
                    int: PyTango.DevLong,
                    float: PyTango.DevDouble,
                    bool: PyTango.DevBoolean,
                    "str": PyTango.DevString,
                    "int": PyTango.DevLong,
                    "float": PyTango.DevDouble,
                    "bool": PyTango.DevBoolean,
                    "None": PyTango.DevVoid,
                    "float_array": PyTango.DevVarFloatArray,
                    "double_array": PyTango.DevVarDoubleArray,
                    "long_array": PyTango.DevVarLongArray,
                    "string_array": PyTango.DevVarStringArray
                }

                """
                CUSTOM COMMANDS
                """
                # Search and adds custom commands.
                _cmd_list = _axis.custom_methods_list()
                elog.debug("'%s' custom commands:" % axis_name)

                new_axis_class_class.cmd_list = dict(BlissAxisClass.cmd_list)

                for (fname, (t1, t2)) in _cmd_list:
                    setattr(new_axis_class, fname, getattr(_axis, fname))

                    tin = types_conv_tab[t1]
                    tout = types_conv_tab[t2]

                    new_axis_class_class.cmd_list.update({fname: [[tin, ""], [tout, ""]]})

                    elog.debug("   %s (in: %s, %s) (out: %s, %s)" % (fname, t1, tin, t2, tout))

                """
                CUSTOM SETTINGS AS ATTRIBUTES.
                """
                elog.debug(" BlissAxisManager.py : %s : -------------- SETTINGS -----------------" % axis_name)

                new_axis_class_class.attr_list = dict(BlissAxisClass.attr_list)

                for setting_name in _axis.settings():
                    if setting_name in ["velocity", "position", "dial_position", "state",
                                        "offset", "low_limit", "high_limit", "acceleration", "_set_position"]:
                        elog.debug(" BlissAxisManager.py -- std SETTING %s " % (setting_name))
                    else:
                        _attr_name = setting_name
                        _setting_type = _axis.controller().axis_settings.convert_funcs[_attr_name]
                        _attr_type = types_conv_tab[_setting_type]
                        elog.debug(" BlissAxisManager.py -- adds SETTING %s as %s attribute" % (setting_name, _attr_type))

                        # Updates Attributes list.
                        new_axis_class_class.attr_list.update({_attr_name:
                                                               [[_attr_type,
                                                                 PyTango._PyTango.AttrDataFormat.SCALAR,
                                                                 PyTango._PyTango.AttrWriteType.READ_WRITE], {
                            'Display level': PyTango._PyTango.DispLevel.OPERATOR,
                            'format': '%10.3f',
                            'description': '%s : u 2' % _attr_name,
                            'unit': 'user units/s^2',
                            'label': _attr_name
                            }]})

                        # Creates functions to read and write settings.
                        def read_custattr(self, attr, _axis=_axis, _attr_name=_attr_name):
                            _val = _axis.get_setting(_attr_name)
                            attr.set_value(_val)
                        new_read_attr_method = types.MethodType(read_custattr, new_axis_class,
                                                                new_axis_class.__class__)
                        setattr(new_axis_class, "read_%s" % _attr_name, new_read_attr_method)

                        def write_custattr(self, attr, _axis=_axis, _attr_name=_attr_name):
                            data = attr.get_write_value()
                            _axis.set_setting(_attr_name, data)

                        new_write_attr_method = types.MethodType(write_custattr, new_axis_class,
                                                                 new_axis_class.__class__)
                        setattr(new_axis_class, "write_%s" % _attr_name, new_write_attr_method)

                # End of custom command and settings
                elog.debug("BlissAxisManager.py : Adds new Axis specific class.")
                py.add_class(new_axis_class_class, new_axis_class)
                elog.debug("BlissAxisManager.py : Class added.")

        elog.debug("BlissAxisManager.py : intitialize server.")
        U.server_init()

    except PyTango.DevFailed:
        print traceback.format_exc()
        elog.exception(
            "Error in server initialization")
        sys.exit(0)

    try:
        bliss_admin_device_names = get_devices_from_server().get('BlissAxisManager')

        if bliss_admin_device_names:
            blname, server_name, device_number = bliss_admin_device_names[
                0].split('/')

            for axis_name in bliss_config.axis_names_list():
                device_name = '/'.join((blname,
                                        '%s_%s' % (server_name, device_number),
                                        axis_name))
                try:
                    elog.debug("Creating %s" % device_name)

                    U.create_device("BlissAxis_%s" % axis_name, device_name)

                except PyTango.DevFailed:
                    # print traceback.format_exc()
                    elog.debug("Device %s already defined in Tango database" % device_name)
                    pass

                # If axis name is not already a tango alias,
                # define it as an alias of the device.
                try:
                    db.get_device_alias(axis_name)
                except PyTango.DevFailed:
                    db.put_device_alias(device_name, axis_name)
                    elog.debug("Created alias %s for device %s" % (axis_name, device_name))

        else:
            # Do not raise exception to be able to use
            # Jive device creation wizard.
            elog.error("No bliss supervisor device",
                       raise_exception=False)

    except PyTango.DevFailed:
        print traceback.format_exc()
        elog.exception(
            "Error in devices initialization")
        sys.exit(0)

    U.server_run()

if __name__ == '__main__':
    main()
