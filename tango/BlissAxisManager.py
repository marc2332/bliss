#!/usr/bin/env python
# -*- coding:utf-8 -*-
import bliss
import bliss.config.motors as bliss_config
import bliss.common.log
import PyTango
import traceback
import TgGevent
import sys
import os
import time
import types


def E_error(msg, raise_exception=True, exception=RuntimeError):
    bliss.common.log.error("[BlissDS] " + msg, raise_exception, exception)


def E_info(msg):
    bliss.common.log.info("[BlissDS] " + msg)


def E_debug(msg):
    bliss.common.log.debug("[BlissDS] " + msg)


def E_exception(msg):
    bliss.common.log.exception("[BlissDS] " + msg)


class BlissAxisManager(PyTango.Device_4Impl):

    def __init__(self, cl, name):
        PyTango.Device_4Impl.__init__(self, cl, name)
        self.debug_stream("In __init__()")
        self.init_device()

    def delete_device(self):
        self.debug_stream("In delete_device() of controller")

    def init_device(self):
        self.debug_stream("In init_device() of controller")
        self.get_device_properties(self.get_device_class())


class BlissAxisManagerClass(PyTango.DeviceClass):

    #    Class Properties
    class_property_list = {
    }

    #    Device Properties
    device_property_list = {
        'config_file':
        [PyTango.DevString,
         "Path to the configuration file",
         []],
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
        self.debug_stream("In __init__()")
        self.init_device()

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
        except:
            self.set_status(traceback.format_exc())

        self.debug_stream("axis found : %s" % self._axis_name)

        self.once = False

        self._init_time = time.time()
        self._t = time.time()

        self.attr_Home_position_read = 0.0
        self.attr_StepSize_read = 0.0
        self.attr_Steps_per_unit_read = 0.0
        """
        self.attr_Steps_read = 0
        self.attr_Position_read = 0.0
        self.attr_Measured_Position_read = 0.0
        self.attr_Acceleration_read = 0.0
        self.attr_Backlash_read = 0.0
        self.attr_HardLimitLow_read = False
        self.attr_HardLimitHigh_read = False
        self.attr_PresetPosition_read = 0.0
        self.attr_FirstVelocity_read = 0.0
        self.attr_Home_side_read = False
        """

    def always_executed_hook(self):
        self.debug_stream("In always_excuted_hook()")

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
                E_exception(
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
        self.debug_stream("In dev_state()")
        argout = PyTango.DevState.UNKNOWN
        #----- PROTECTED REGION ID(TOTO.State) ENABLED START -----#

        try:
            _state = self.axis.state()
            if _state == bliss.common.axis.READY:
                self.set_state(PyTango.DevState.ON)
            elif _state == bliss.common.axis.MOVING:
                self.set_state(PyTango.DevState.MOVING)
            else:
                self.set_state(PyTango.DevState.FAULT)
                self.set_status("BlissAxisManager axis not READY nor MOVING...")
        except:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status(traceback.format_exc())

        # ----- PROTECTED REGION END -----#      //      TOTO.State
        if argout != PyTango.DevState.ALARM:
            PyTango.Device_4Impl.dev_state(self)
        return self.get_state()

    def read_Steps_per_unit(self, attr):
        self.debug_stream("In read_Steps_per_unit()")
        attr.set_value(self.axis.steps_per_unit())

    def write_Steps_per_unit(self, attr):
        self.debug_stream("In write_Steps_per_unit()")
        # data = attr.get_write_value()
        E_debug("Not implemented")

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
        _t = time.time()
        attr.set_value(self.axis.position())
        _duration = time.time() - _t
        if _duration > 0.05:
            print "{%s} read_Position : duration seems too long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)

    def write_Position(self, attr):
        """
        Sends movement command to BlissAxisManager axis.
        NB : take care to call WaitMove before sending another movement
        self.write_position_wait is a device property (False by default).
        """
        self.debug_stream("In write_Position()")
        #self.axis.move(attr.get_write_value(), wait=False)
        #self.axis.move(attr.get_write_value(), wait=True)
        self.axis.move(attr.get_write_value(), wait=self.write_position_wait)

    def read_Measured_Position(self, attr):
        self.debug_stream("In read_Measured_Position()")
        _t = time.time()
        attr.set_value(self.axis.measured_position())
        _duration = time.time() - _t

        if _duration > 0.01:
            print "{%s} read_Measured_Position : duration seems too long : %5.3g ms" % \
                (self._ds_name, _duration * 1000)

    def read_Acceleration(self, attr):
        try:
            _acc = self.axis.acceleration()
            self.debug_stream("In read_Acceleration(%f)" % float(_acc))
            attr.set_value(_acc)
        except:
            # E_exception("Unable to read acceleration for this axis")
            pass

    def write_Acceleration(self, attr):
        try:
            data = float(attr.get_write_value())
            self.debug_stream("In write_Acceleration(%f)" % data)
            self.axis.acceleration(data)
        except:
            E_exception("Unable to write acceleration for this axis")

    def read_AccTime(self, attr):
        self.debug_stream("In read_AccTime()")
        attr.set_value(self.attr_AccTime_read)

    def write_AccTime(self, attr):
        data = attr.get_write_value()
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
        attr.set_value(self.attr_Backlash_read)

    def write_Backlash(self, attr):
        self.debug_stream("In write_Backlash()")
        #data = attr.get_write_value()

    def read_Home_position(self, attr):
        self.debug_stream("In read_Home_position()")
        attr.set_value(self.attr_Home_position_read)

    def write_Home_position(self, attr):
        self.debug_stream("In write_Home_position()")
        data = float(attr.get_write_value())
        self.attr_Home_position_read = data

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
        # data = attr.get_write_value()

    def read_FirstVelocity(self, attr):
        self.debug_stream("In read_FirstVelocity()")
        attr.set_value(self.attr_FirstVelocity_read)

    def write_FirstVelocity(self, attr):
        self.debug_stream("In write_FirstVelocity()")
        # data = attr.get_write_value()

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

    #-------------------------------------------------------------------------
    #    Motor command methods
    #-------------------------------------------------------------------------
    def On(self):
        """ Enable power on motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In On()")
        self.axis.on()

        if self.axis.state() == "READY":
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
        if self.axis.state() == "OFF":
            self.set_state(PyTango.DevState.OFF)
        else:
            self.set_state(PyTango.DevState.FAULT)
            self.set_status("OFF command was not executed as expected.")

    def GoHome(self):
        """ Move the motor to the home position given by a home switch.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In GoHome(%f)" % self.attr_Home_position_read)
        self.axis.home(self.attr_Home_position_read, wait=False)

    def Abort(self):
        """ Stop immediately the motor

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In Abort()")
        self.axis.stop()

    def StepUp(self):
        """ perform a relative motion of ``stepSize`` in the forward
         direction.  StepSize is defined as an attribute of the
         device.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepUp()")

    def StepDown(self):
        """ perform a relative motion of ``stepSize`` in the backward
         direction.  StepSize is defined as an attribute of the
         device.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In StepDown()")

    def GetInfo(self):
        """ provide information about the axis.

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevString """
        self.debug_stream("In GetInfo()")
        return self.axis.get_info()

    def RawCom(self, argin):
        """ send a raw command to the axis. Be carefull!

        :param argin: String with command
        :type: PyTango.DevString
        :return:
        :rtype: PyTango.DevString """
        self.debug_stream("In RawCom()")
        return self.axis.raw_com(argin)

    def WaitMove(self):
        """ Waits end of last motion

        :param :
        :type: PyTango.DevVoid
        :return:
        :rtype: PyTango.DevVoid """
        self.debug_stream("In WaitMove()")
        return self.axis.wait_move()


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
        'StepUp':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"], {'Display level': PyTango.DispLevel.EXPERT, }],
        'StepDown':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"], {'Display level': PyTango.DispLevel.EXPERT, }],
        'GetInfo':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevString, "Info string returned by the axis"]],
        'RawCom':
        [[PyTango.DevString, "Raw command to be send to the axis. Be carefull!"],
         [PyTango.DevString, "Answer provided by the axis"],
         {'Display level': PyTango.DispLevel.EXPERT, }],
        'WaitMove':
        [[PyTango.DevVoid, "none"],
         [PyTango.DevVoid, "none"]],
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
             'unit': "units/s^2",
             'format': "%10.3f",
             'description': "The acceleration of the motor.",
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
             'description': "The acceleration time of the motor.",
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
          PyTango.READ_WRITE],
         {
             'label': "Backlash",
             'unit': "uu",
             'format': "%5.3f",
             'description': "Backlash to be applied to each motor movement",
             'Display level': PyTango.DispLevel.EXPERT,
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
    }


def get_devices_from_server():
    # get sub devices
    fullpathExecName = sys.argv[0]
    execName = os.path.split(fullpathExecName)[-1]
    execName = os.path.splitext(execName)[0]
    personalName = '/'.join([execName, sys.argv[1]])
    db = PyTango.Database()
    result = db.get_device_class_list(personalName)

    #"result" is :  DbDatum[
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
        E_info(
            "Deleting existing BlissAxisManager axis: %s" %
            _axis_device_name)
        db.delete_device(_axis_device_name)


def delete_unused_bliss_axes():
    """
    Removes BlissAxisManager axes that are not running.
    """
    # get BlissAxis (only from current instance).
    bliss_axis_device_names = get_devices_from_server().get('BlissAxis')
    E_info("Axes: %r" % bliss_axis_device_names)


def main():
    try:
        delete_unused_bliss_axes()
    except:
        E_error(
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
                bliss.common.log.level(40)
            elif tango_log_level == 2:
                bliss.common.log.level(30)
            elif tango_log_level == 3:
                bliss.common.log.level(20)
            else:
                bliss.common.log.level(10)
        else:
            # by default : show INFO
            bliss.common.log.level(20)
            tango_log_level = 0

        E_info("tango log level=%d" % tango_log_level)
        E_debug("BlissAxisManager.py debug message")
        E_error("BlissAxisManager.py error message", raise_exception=False)

        # Searches for bliss devices defined in tango database.
        db = py.instance().get_database()
        device_list = get_devices_from_server().get('BlissAxisManager')

        if device_list is not None:
            _device = device_list[0]
            E_debug("BlissAxisManager.py - Found device : %s" % _device)
            _config_file = db.get_device_property(
                _device, "config_file")[
                "config_file"][
                0]
            E_info("BlissAxisManager.py - config file : %s" % _config_file)
            first_run = False
        else:
            print "[FIRST RUN] New server never started ? -> no database entry..."
            print "[FIRST RUN] NO CUSTOM COMANDS :( "
            print "[FIRST RUN] Restart DS to havec CUSTOM COMMANDS"
            first_run = True

        py.add_class(BlissAxisManagerClass, BlissAxisManager)
        py.add_class(BlissAxisClass, BlissAxis)

        U = PyTango.Util.instance()

        if not first_run:
            TgGevent.execute(bliss.load_cfg, _config_file)

            # Get axis names defined in config file.
            axis_names = bliss_config.axis_names_list()
            E_debug("axis names list : %s" % axis_names)

            # Takes one axis...
            axis_name = axis_names[0]
            _axis = TgGevent.get_proxy(bliss.get_axis, axis_name)

            types_conv_tab = {
                None: PyTango.DevVoid,
                str: PyTango.DevString,
                int: PyTango.DevLong,
                float: PyTango.DevDouble}

            # Search and adds custom commands.
            _cmd_list = _axis.custom_methods_list()
            E_debug("BlissAxisManager.py - '%s' custom commands:" % axis_name)
            for (fname, (t1, t2)) in _cmd_list:
                # adding a method should be like that but does not work :(
                # setattr(BlissAxis, fname, types.MethodType(getattr(_axis, fname), None, BlissAxis) )

                # ugly verison by CG... MG has not benn involved in such crappy code (but it works:))
                setattr(BlissAxis, fname, getattr(_axis, fname))

                tin = types_conv_tab[t1]
                tout = types_conv_tab[t2]
                BlissAxisClass.cmd_list.update({fname: [[tin, ""], [tout, ""]]})
                E_debug("   %s (in: %s, %s) (out: %s, %s)" % (fname, t1, tin, t2, tout))

        U.server_init()

    except PyTango.DevFailed:
        print traceback.format_exc()
        E_exception(
            "Error in server initialization",
            raise_exception=False)
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
                    E_debug("BlissAxisManager.py - Creating %s" % device_name)
                    U.create_device('BlissAxis', device_name)
                except PyTango.DevFailed:
                    # print traceback.format_exc()
                    pass
        else:
            # Do not raise exception to be able to use
            # Jive device creation wizard.
            E_error("No bliss supervisor device",
                              raise_exception=False)
    except PyTango.DevFailed:
        print traceback.format_exc()
        E_exception(
            "Error in devices initialization",
            raise_exception=False)
        sys.exit(0)

    U.server_run()

if __name__ == '__main__':
    main()
