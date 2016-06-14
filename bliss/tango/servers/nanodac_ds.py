# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import PyTango
import TgGevent
from bliss.controllers.temperature.eurotherm import nanodac

class _CallableRead:
    def __init__(self,obj,name) :        
        self.__obj = obj
        self.__name = name

    def __call__(self,attr) :
        attr.set_value(getattr(self.__obj,self.__name)())
        
class _CallableWrite:
    def __init__(self,obj,name) :        
        self.__obj = obj
        self.__name = name

    def __call__(self,attr) :
        value = attr.get_write_value()
        o_property = getattr(self.__obj,self.__name,value)
        o_property(value)

class Nanodac(PyTango.Device_4Impl) :
    def __init__(self,*args) :
        PyTango.Device_4Impl.__init__(self,*args)
        self.init_device()

    def init_device(self) :
        self.set_state(PyTango.DevState.ON)
        self.get_device_properties(self.get_device_class())
        self._nanodac = TgGevent.get_proxy(nanodac.nanodac,'server',{"controller_ip":self.controller_ip})
        self._ramp1 = TgGevent.get_proxy(self._nanodac.get_soft_ramp,1)
        self._ramp2 = TgGevent.get_proxy(self._nanodac.get_soft_ramp,2)
        self._c1 = TgGevent.get_proxy(self._nanodac.get_channel,1)
        self._c2 = TgGevent.get_proxy(self._nanodac.get_channel,2)
        self._c3 = TgGevent.get_proxy(self._nanodac.get_channel,3)
        self._c4 = TgGevent.get_proxy(self._nanodac.get_channel,4)
    
    def __getattr__(self,name):
        if name.startswith('read_') or name.startswith('write_') :
            try:
                _,mod_name,attr_name = name.split('_')
                mod = getattr(self,'_%s' % mod_name)
            except ValueError:
                _,main_mod_name,mod_name,attr_name = name.split('_')
                main_mod = getattr(self,'_%s' % main_mod_name)
                main_mod = main_mod.get_base_obj()
                mod = TgGevent.get_proxy(getattr,main_mod,mod_name)

            if name.startswith('read_'):
                func = _CallableRead(mod,attr_name)
            else:
                func = _CallableWrite(mod,attr_name)
            self.__dict__[name] = func
            return func

        raise AttributeError("Nanodac has no attribute %s" % name)

    def stop(self):
        self._ramp.stop()

class NanodacClass(PyTango.DeviceClass) :
    #    Class Properties
    class_property_list = {
        }

    #    Device Properties
    device_property_list = {
        'controller_ip' :
        [PyTango.DevString,
         "Ethernet ip address",[]],
        }
    #    Command definitions
    cmd_list = {
        'stop':
        [[PyTango.DevVoid, ""],
         [PyTango.DevVoid, ""]],
       }

     #    Attribute definitions
    attr_list = {
        #Ramp1
        'ramp1_slope':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp1_workingsp':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'ramp1_targetsp':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp1_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'ramp1_pid_derivativetime':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp1_pid_integraltime':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp1_pid_proportionalband':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        #Ramp2
        'ramp2_slope':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp2_workingsp':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'ramp2_targetsp':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp2_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'ramp2_pid_derivativetime':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp2_pid_integraltime':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        'ramp2_pid_proportionalband':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ_WRITE]],
        #Channel 1
        'c1_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c1_pv2':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c1_type':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        'c1_lintype':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        #Channel 2
        'c2_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c2_pv2':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c2_type':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        'c2_lintype':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        #Channel 3
        'c3_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c3_pv2':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c3_type':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        'c3_lintype':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        #Channel 4
        'c4_pv':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c4_pv2':
        [[PyTango.DevDouble,
          PyTango.SCALAR,
          PyTango.READ]],
        'c4_type':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],
        'c4_lintype':
        [[PyTango.DevString,
          PyTango.SCALAR,
          PyTango.READ]],

        }

def main():
    try:
        py = PyTango.Util(sys.argv)
        py.add_TgClass(NanodacClass,Nanodac,'Nanodac')
        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()
    except:
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
