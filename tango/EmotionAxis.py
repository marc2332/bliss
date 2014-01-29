#!/usr/bin/env python
# -*- coding:utf-8 -*- 
import bliss
import PyTango
import traceback
import TgGevent
import sys
## Device States Description
## ON : The motor powered on and is ready to move.
## MOVING : The motor is moving
## FAULT : The motor indicates a fault.
## ALARM : The motor indicates an alarm state for example has reached
##         a limit switch.
## OFF : The power on the moror drive is switched off.
## DISABLE : The motor is in slave mode and disabled for normal use

class BlissAxis(PyTango.Device_4Impl):
    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        self.debug_stream("In __init__()")
        self.init_device()
        
    def delete_device(self):
        self.debug_stream("In delete_device()")

    def init_device(self):
        self.debug_stream("In init_device()")
        self.get_device_properties(self.get_device_class())

        try:
            bliss.load_cfg(self.config_file)
            self.axis = TgGevent.wrap(bliss.get_axis(self.axis_name))
        except:
            self.set_status(traceback.format_exc())
         
        """
        self.attr_Steps_per_unit_read = 0.0
        self.attr_Steps_read = 0
        self.attr_Position_read = 0.0
        self.attr_Acceleration_read = 0.0
        self.attr_Velocity_read = 0.0
        self.attr_Backlash_read = 0.0
        self.attr_Home_position_read = 0.0
        self.attr_HardLimitLow_read = False
        self.attr_HardLimitHigh_read = False
        self.attr_PresetPosition_read = 0.0
        self.attr_FirstVelocity_read = 0.0
        self.attr_Home_side_read = False
        self.attr_StepSize_read = 0.0
        """

    def dev_state(self):
        """ This command gets the device state (stored in its device_state data member) and returns it to the caller.
        
        :param : none
        :type: PyTango.DevVoid
        :return: Device state
        :rtype: PyTango.CmdArgType.DevState """
        self.debug_stream("In dev_state()")
        argout = PyTango.DevState.UNKNOWN
        #----- PROTECTED REGION ID(TOTO.State) ENABLED START -----#

        try:
          if self.axis.state() == bliss.common.axis.READY:
            self.set_state(PyTango.DevState.ON)
          elif self.axis.state() == bliss.common.axis.MOVING:
            self.set_state(PyTango.DevState.MOVING)
          else:
            self.set_state(PyTango.DevState.FAULT)
        except:
          self.set_state(PyTango.DevState.FAULT)

        #----- PROTECTED REGION END -----#      //      TOTO.State
        if argout != PyTango.DevState.ALARM:
            PyTango.Device_4Impl.dev_state(self)
        return self.get_state()


    def dev_status(self):
        """ This command gets the device status (stored in its device_status data member) and returns it to the caller.
        
        :param : none
        :type: PyTango.DevVoid
        :return: Device status
        :rtype: PyTango.ConstDevString """
        self.debug_stream("In dev_status()")
        argout = ''
        #----- PROTECTED REGION ID(TOTO.Status) ENABLED START -----#

        #----- PROTECTED REGION END -----#      //      TOTO.Status
        self.set_status(self.argout)
        self.__status = PyTango.Device_4Impl.dev_status(self)
        return self.__status

    def read_Steps_per_unit(self, attr):
        self.debug_stream("In read_Steps_per_unit()")
        attr.set_value(self.attr_Steps_per_unit_read)
        
    def write_Steps_per_unit(self, attr):
        self.debug_stream("In write_Steps_per_unit()")
        data=attr.get_write_value()
        
    def read_Steps(self, attr):
        self.debug_stream("In read_Steps()")
        attr.set_value(self.attr_Steps_read)
        
    def write_Steps(self, attr):
        self.debug_stream("In write_Steps()")
        data=attr.get_write_value()
        
    def read_Position(self, attr):
        self.debug_stream("In read_Position()")
        attr.set_value(self.axis.position())
        
    def write_Position(self, attr):
        self.debug_stream("In write_Position()")
        self.axis.move(attr.get_write_value(), wait=False)
        
    def read_Acceleration(self, attr):
        self.debug_stream("In read_Acceleration()")
        attr.set_value(self.attr_Acceleration_read)
        
    def write_Acceleration(self, attr):
        self.debug_stream("In write_Acceleration()")
        data=attr.get_write_value()
        
    def read_Velocity(self, attr):
        self.debug_stream("In read_Velocity()")
        attr.set_value(self.attr_Velocity_read)
        
    def write_Velocity(self, attr):
        self.debug_stream("In write_Velocity()")
        data=attr.get_write_value()
        
    def read_Backlash(self, attr):
        self.debug_stream("In read_Backlash()")
        attr.set_value(self.attr_Backlash_read)
        
    def write_Backlash(self, attr):
        self.debug_stream("In write_Backlash()")
        data=attr.get_write_value()
        
    def read_Home_position(self, attr):
        self.debug_stream("In read_Home_position()")
        attr.set_value(self.attr_Home_position_read)
        
    def write_Home_position(self, attr):
        self.debug_stream("In write_Home_position()")
        data=attr.get_write_value()
        
    def read_HardLimitLow(self, attr):
        self.debug_stream("In read_HardLimitLow()")
        attr.set_value(self.attr_HardLimitLow_read)
        
    def read_HardLimitHigh(self, attr):
        self.debug_stream("In read_HardLimitHigh()")
        attr.set_value(self.attr_HardLimitHigh_read)
        
    def read_PresetPosition(self, attr):
        self.debug_stream("In read_PresetPosition()")
        attr.set_value(self.attr_PresetPosition_read)
        
    def write_PresetPosition(self, attr):
        self.debug_stream("In write_PresetPosition()")
        data=attr.get_write_value()
        
    def read_FirstVelocity(self, attr):
        self.debug_stream("In read_FirstVelocity()")
        attr.set_value(self.attr_FirstVelocity_read)
        
    def write_FirstVelocity(self, attr):
        self.debug_stream("In write_FirstVelocity()")
        data=attr.get_write_value()
        
    def read_Home_side(self, attr):
        self.debug_stream("In read_Home_side()")
        attr.set_value(self.attr_Home_side_read)
        
    def read_StepSize(self, attr):
        self.debug_stream("In read_StepSize()")
        attr.set_value(self.attr_StepSize_read)
        
    def write_StepSize(self, attr):
        self.debug_stream("In write_StepSize()")
        data=attr.get_write_value()
            
    def read_attr_hardware(self, data):
        self.debug_stream("In read_attr_hardware()")

    #-----------------------------------------------------------------------------
    #    Motor command methods
    #-----------------------------------------------------------------------------
    def On(self):
        """ Enable power on motor
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In On()")
        
    def Off(self):
        """ Desable power on motor
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Off()")
        
    def GoHome(self):
        """ Move the motor to the home position given by a home switch.
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In GoHome()")
        
    def Abort(self):
        """ Stop immediately the motor
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Abort()")
        self.axis.stop()
        
    def StepUp(self):
        """ perform a relative motion of ``stepSize`` in the forward direction.
         StepSize is defined as an attribute of the device.
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepUp()")
        
    def StepDown(self):
        """ perform a relative motion of ``stepSize`` in the backward direction.
         StepSize is defined as an attribute of the device.
        
        :param : 
        :type: PyTango.DevVoid
        :return: 
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepDown()")
        

class BlissAxisClass(PyTango.DeviceClass):
    #    Class Properties
    class_property_list = {
        }

    #    Device Properties
    device_property_list = {
        'config_file':
            [PyTango.DevString,
            "Path to the configuration file",
            [] ],
        'axis_name':
            [PyTango.DevString,
            "axis name in config file",
            [] ],
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
        'StepUp':
            [[PyTango.DevVoid, "none"],
            [PyTango.DevVoid, "none"]],
        'StepDown':
            [[PyTango.DevVoid, "none"],
            [PyTango.DevVoid, "none"]],
        }


    #    Attribute definitions
    attr_list = {
        'Steps_per_unit':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Steps per mm",
                'unit': "steps/mm",
                'format': "%7.1f",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'Steps':
            [[PyTango.DevLong,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Steps",
                'unit': "steps",
                'format': "%6d",
                'description': "number of steps in the step counter\n",
                'Memorized':"true"
            } ],
        'Position':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "position",
                'unit': "mm",
                'format': "%7.3f",
                'description': "The actual motor position.",
            } ],
        'Acceleration':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Acceleration",
                'unit': "units/s^2",
                'format': "%.3f",
                'description': "The acceleration of the motor.",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'Velocity':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Velocity",
                'unit': "units/s",
                'format': "%.3f",
                'description': "The constant velocity of the motor.",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'Backlash':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Backlash",
                'unit': "mm",
                'format': "%5.3f",
                'description': "Backlash to be applied to each motor movement",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'Home_position':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Home position",
                'unit': "mm",
                'format': "%7.3f",
                'description': "Position of the home switch",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'HardLimitLow':
            [[PyTango.DevBoolean,
            PyTango.SCALAR,
            PyTango.READ],
            {
                'label': "low limit switch state",
            } ],
        'HardLimitHigh':
            [[PyTango.DevBoolean,
            PyTango.SCALAR,
            PyTango.READ],
            {
                'label': "up limit switch state",
            } ],
        'PresetPosition':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "Preset Position",
                'unit': "mm",
                'format': "%.3f",
                'description': "preset the position in the step counter",
                'Display level': PyTango.DispLevel.EXPERT,
            } ],
        'FirstVelocity':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'label': "first step velocity",
                'unit': "units/s",
                'format': "%.3f",
                'description': "number of unit/s for the first step and for the move reference",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        'Home_side':
            [[PyTango.DevBoolean,
            PyTango.SCALAR,
            PyTango.READ],
            {
                'description': "indicates if the axis is below or above the position of the home switch",
            } ],
        'StepSize':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            {
                'unit': "mm",
                'format': "%.3f",
                'description': "Size of the relative step performed by the StepUp and StepDown commands.\nThe StepSize is expressed in physical unit.",
                'Display level': PyTango.DispLevel.EXPERT,
                'Memorized':"true"
            } ],
        }


def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_class(BlissAxisClass,BlissAxis,'BlissAxis')

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e

if __name__ == '__main__':
    main()
