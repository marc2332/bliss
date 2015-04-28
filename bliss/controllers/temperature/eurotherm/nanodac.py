# This class is the main controller of Eurotherm nanodac
import weakref
import os
import time

import gevent

from bliss.comm import modbus
from .nanodac_mapping import name2address
from . import nanodac_mapping

def _get_read_write(modbus,address_read_write):
    address,value_type = address_read_write
    if isinstance(address,tuple):
        address_read,value_type_read = address
        address_write,value_type_write,nb_digit = value_type
        def read(self):
            return modbus.read_holding_register(address_read,value_type_read)
        def write(self,value):
            if nb_digit >= 1:
                write_value = value * 10 * nb_digit
            else:
                write_value = value
            return modbus.write_holding_register(address_write,value_type_write,write_value)
        return read,write
    else:
        if hasattr(nanodac_mapping,value_type): # probably an enum
            enum_type = getattr(nanodac_mapping,value_type)
            def read(self):
                value = modbus.read_holding_register(address,'b')
                return enum_type.get(value,'Unknown')
            def write(self,value):
                if isinstance(value,str):
                    for k,v in enum_type.iteritems():
                        if v.lower() == value.lower():
                            value = k
                            break;
                    else:
                        raise RuntimeError("Value %s is not in enum (%s)",value,
                                           enum_type.values())
                return modbus.write_holding_register(address,'b',value)
        else:
            def read(self) :
                return modbus.read_holding_register(address,value_type)
            def write(self,value):
                return modbus.write_holding_register(address,value_type,value)
        return read,write

def _create_attribute(filter_name,cls,instance,modbus):
    for name,address_read_write in name2address.iteritems():
        if name.startswith(filter_name) :
            subnames = name[len(filter_name) + 1:].split('.')
            read,write = _get_read_write(modbus,address_read_write)
            if len(subnames) > 1:
                if subnames[0] == 'main':
                    setattr(cls,subnames[1],property(read,write))
                elif getattr(instance,subnames[0],None) is None:
                    sub_cls = type('.'.join([cls.__module__,cls.__name__,subnames[0]]),(),{})
                    child_instance = sub_cls()
                    _create_attribute(filter_name + '.' + subnames[0],sub_cls,instance,modbus)
                    setattr(instance,subnames[0],child_instance)
            else:
                setattr(cls,subnames[0],property(read,write))
    
class nanodac(object):
    class SoftRamp(object) :
        def __init__(self,nanodac,loop_number) :
            self._loop = nanodac.get_loop(loop_number)
            self._slope = 1/60. # default 1 deg / min
            self._targetsp = self._loop.targetsp
            self._ramp_task = None
            self._pipe = os.pipe()

        def __getattr__(self,name):
            return getattr(self._loop,name)

        @property
        def slope(self):
            return self._slope
        @slope.setter
        def slope(self,val) :
            self._slope = val
            os.write(self._pipe[1],'|')

        @property
        def workingsp(self):
            return self._loop.targetsp

        @property
        def targetsp(self) :
            return self._targetsp

        @targetsp.setter
        def targetsp(self,val) :
            self._started_targetsp = self._loop.pv
            self._targetsp = val
            self._start_ramp = time.time()

            if self._ramp_task is None:
                self._ramp_task = gevent.spawn(self._run)
            else:
                os.write(self._pipe[1],'|')
                
        @property
        def pv(self):
            return self._loop.pv

        def stop(self) :
            self._targetsp = self._loop.targetsp
            os.write(self._pipe[1],'|')

        def _run(self) :
            while abs(self._targetsp - self._loop.targetsp) > 0.1:
                wait_time = 0.1 / self._slope
                if wait_time < 0.: wait_time = 0.
                fd,_,_ = gevent.select.select([self._pipe[0]],[],[],wait_time)
                if fd: os.read(self._pipe[0],1024)
                targetsp = self._slope * (time.time() - self._start_ramp) + self._started_targetsp
                if targetsp > self._targetsp: targetsp = self._targetsp
                try:
                    self._loop.targetsp = round(targetsp,1)
                except:
                    import traceback
                    traceback.print_exc()
                    break
            self._ramp_task = None

    def __init__(self,name,config_tree) :
        self.name = name
        self._modbus = modbus.ModbusTcp(config_tree["controller_ip"])
    
    def _get_address(self,name) :
        name_key = name.lower()
        try:
            address,value_type = name2address[name_key]
        except KeyError:
            raise RuntimeError("%s doesn't exist in address mapping" % name)
        else:
            return address,value_type

    def read(self,name) :
        address,value_type = self._get_address(name)
        if isinstance(address,tuple): address,value_type = address
        return self._modbus.read_holding_register(address,value_type)

    def write(self,name,value):
        address,value_type = self._get_address(name)
        if isinstance(address,tuple): 
            address,value_type,nb_digit = value_type
            if nb_digit >= 1:
                value = value * 10 * nb_digit
        self._modbus.write_holding_register(address,value_type,value)
    
    def _get_handler(self,filter_name) :
        cls = type('.'.join([self.__class__.__module__,
                             self.__class__.__name__,filter_name]),(),{})
        instance = cls()
        _create_attribute(filter_name,cls,instance,self._modbus)
        return instance
        
    def get_channel(self,channel_number) :
        if 1 <= channel_number <= 4:
            return self._get_handler('channel.%d' % channel_number)
        else:
            raise RuntimeError("Nanodac doesn't have channel %d" % channel_number)

    def get_loop(self,loop_number) :
        if 1 <= loop_number <= 2:
            return self._get_handler('loop.%d' % loop_number)
        else:
            raise RuntimeError("Nanodac doesn't have loop %d" % loop_number)

    def get_soft_ramp(self,loop_number) :
        return self.SoftRamp(self,loop_number)
