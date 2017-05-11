# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""

This is a skeleton for writing a temperature controller called MyTemperatureController

1- A beacon .yml file has to be defined.
   This file will define :
   - 'inputs'    : the list of Input type objects for this controller.
   - 'outputs'   : the list of Output type objects for this controller.
   - 'ctrl_loops': the list of Loop type objects for this controller.

   Following, an example is given, providing 
   - 2 Input type  objects: used for reading only. can be seen as sensors.
   - 1 Output type object : reading, ramping can be performed on such object. 
                            can be seen as heater
   - 1 Loop object        : to perform a regulation between an Input type object
                            and an Output type object

   In this example, it is shown also what is 'mandatory', what is 'recommended',
   and what is needed if you want a Tango server control.
   - mandatory: 
          - 'name': for all objects, a 'name' is mandatory.
          - 'input'/'output': For a 'loops' object only. you must provide the names of the
                            'inputs' object and 'outputs' object used for the regulation.

   - recommended: for the 'outputs' objects 
          - 'low_limit'/'high_limit': you can provide these values if you need a filtering
            of the setpoints that you will send on you object. A RunTimeError with a
            message will be sent if you try to setpoint outside these limits
          - 'deadband': when you ramp to a setpoint, it allows to know when you have
            readched the setpoint (inside this deadband), using the 'rampstate' method.

   - for Tango server generation:
          - 'tango_server': name of the server generation.
                            In this example, it will be generating when running it as:
                                     BlissTempManager temp1

   Then, you can add any property you will need in you own code

---------------------------------------------
controller:
    class: MyTemperatureController
    inputs:
        - 
            name: thermo_sample        <- mandatory
            channel: A       
            tango_server: temp1        <- for Tango server
        - 
            name: sensor               <- mandatory
            channel: B       
            tango_server: temp1        <- for Tango server
    outputs: 
        -
            name: heater               <- mandatory
            channel: 1       
            low_limit: 10              <- recommended
            high_limit: 200            <- recommended
            deadband: 0.1              <- recommended
            tango_server: temp1        <- for Tango server
    ctrl_loops:
        -
            name: sample_regulation    <- mandatory
            input: $thermo_sample      <- mandatory
            output: $heater            <- mandatory
            tango_server: temp1        <- for Tango server

---------------------------------------------

2- In the following skeleton 'MyTemperatureController' class, the methods
   that must be written are documented.
   It can be noted also the following things:

   - Most of the methods receive as an argument the object from which they
     are called (name 'tinput', 'toutput' and 'tloop').
     A dictionnary has been defined for all these objects, in which it is
     easy for a TempController writer to store any useful data concerning one
     specific object: 
         tinput._attr_dict
         toutput._attr_dict
         tloop._attr_dict
     These dictionnaries can be used freely by a TempController writer. As they
     are visible from the outside world, the '_' has been used in front of the name
     to protect its use, and to mention to a final client of a controller not to try 
     to use them ...
     
     
"""
from bliss.comm import modbus
from bliss.comm.exceptions import CommunicationError, CommunicationTimeout


""" TempController import """
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop
from bliss.common import log
from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set

class Eurotherm2000Error(CommunicationError):
    pass

class Eurotherm2000:

    def __init__(self, modbus_address, serialport):
        #9600 baud, 8 bits, no parity, 1 stop bit, so Serial default usually
        log.debug("Eurotherm2000:__init__ (address %d, port %s)"%( modbus_address, serialport))
        self.device = modbus.Modbus_RTU (modbus_address, serialport)
        self.setpointvalue=None 
        
    def __del__ (self):
        self.close()
        
    def close (self):
        print "close method for Eurotherm2000 class; closing", self
        self.device._serial.close()

    def initialize (self):
        print "Eurotherm2000:initialize"
        ident = self.identification()
        version = self.firmware()
        self.resolution()
        print "eurotherm %s (firmware: %s) connected to serial port: %s" % (ident,version,self.device._serial)

    def identification (self):

        # ident now contains a number in hex format which will identify your controller.
        #    in format >ABCD (hex),
        #    A = 2 (series 2000) B = Range number  C = Size       D = Type
        #                          2: 2200           3: 1/32 din    0: PID/on-off
        #                          4: 2400           6: 1/16 din    2: VP
        #                                            8: 1/8 din
        #                                            4: 1/4 din
        
        ident = self.device.read_holding_registers (122, 'H')
        if ident>>12 is 2:
            print "Connected to Eurotherm %x" % (ident)
            self.ident=ident
            return ident
        else:
            raise Eurotherm2000Error ("Device with identification number %x is not an Eurotherm series 2000 device, cannot be controlled, disconnecting..." %(ident))
            self.close()

    def firmware (self):
                    
        # There is the possibility to config the 2400 series with floating point
        # or integer values. Tag address 525 tells you how many digits appear
        # after the radix character. BUT !!!!! there was one controller with
        # firmware version 0x0411, on which this cell`s contents has no influence
        # on the modbus readings. The sample environment controllers have the
        # 0x0461 version.

        version = self.device.read_holding_registers (107, 'H')
        print "Firmware V%x.%x" % ((version&0xff00)>>8 , (version&0x00ff))
        return version

    def resolution (self):
        if ((self.ident&0xf00)>>8) is 4:
            resol = self.device.read_holding_registers (12550, 'H')#0:full, 1:integer or the oposite
            decimal = self.device.read_holding_registers (525, 'H')#0:0, #1:1, 2:2
        elif ((self.ident&0xf00)>>8) is 7:
            resol = self.device.read_holding_registers (12275, 'H')#0:full, 1:integer 
            decimal = self.device.read_holding_registers (5076, 'H')#0:0, #1:1, 2:2
        else:
            raise Eurotherm2000Error ("Device with identification number %x is not supported, cannot be controlled, disconnecting..." %(ident))
            self.close()
            return

        self.scale = pow(10,decimal)

    def setpoint (self, value):
        self.setpointvalue=value
        value*=self.scale
        self.device.write_registers(2,'H',value)

    def get_setpoint (self, address = 2):
        if address is not 5: #working setpoint rather than setp
            address = 2
        value = self.device.read_holding_registers(address,'H')
        value/=self.scale
        if address is 2:
            self.setpointvalue=value
        return value

    def pv (self):
        value = self.device.read_holding_registers(1,'H')
        value/=self.scale
        self.pv=value
        return value

    def op (self):
        value = self.device.read_holding_registers(3,'H')
        value/=self.scale
        self.op=value
        return value

    def abort (self):

        if self.sp_status() is 2:
            raise Eurotherm2000Error ("cannot abort, an internal program is running; first RESET device")
        
        self.setpoint(self.pv())
            

    def set_ramprate (self,value):
        self.rate=value
#        value*=self.scale
        self.device.write_registers(35,'H',value)

        
    def get_ramprate (self):
        value = self.device.read_holding_registers(35,'H')
#        value/=self.scale
        self.rate=value
        return value
        
        
    def sp_status (self):
        #0: ready
        #1: wsp != sp so running
        #2: busy, a program is running
        
        if ((self.ident&0xf00)>>8) is 4 and self.device.read_holding_registers(23,'H') is not 1:
            return 2
        else:
            sp = self.get_setpoint(2)
            wsp = self.get_setpoint(5)
            if sp is not wsp:
                return 1
            else:
                return 0

    def device_status(self):
#        import pdb;pdb.set_trace()
        
        _status= ["Alarm 1","Alarm 2","Alarm 3","Alarm 4","Manual mode","Sensor broken","Open loop","Heater fail","Auto tune active","Ramp program complete","PV out of range","DC control module fault","Programmer Segment Sync running","Remote input sensor break"]
        
        value = self.device.read_holding_registers(74,'H') # Fast Status Byte

        for i in range(len(_status)):
            
            if pow(2,i)&value:
                print _status[i]
        
        return value
                
    def _rd (self, address, format = 'H'):
        return self.device.read_holding_registers (address, format)

    def _wr (self, address, format, value):
        return self.device.write_registers (address, format, value)
        
            
    def pid (self):
        value = self.device.read_holding_registers(6,'HHHH')
        _pid = (value[0]/self.scale, value[2],value[3])
        return _pid


    

class eurotherm2000(Controller):

    def __init__(self, config, *args):
        """ 
        controller configuration
        """
        log.debug("eurotherm2000:__init__ (%s %s)"%( config, args))

        self._dev = Eurotherm2000(1, config["port"])
        Controller.__init__(self, config, *args)

    def __del__ (self):
        self._dev.close()

    def initialize(self):
        print "eurotherm2000:initialize"
        self._dev.initialize()
        
    def initialize_input(self,tinput):
        print "eurotherm2000:initialize_input"
        if 'type' not in tinput.config:
            tinput.config['type']='pv'
        
    def initialize_output(self,toutput):
        print "eurotherm2000:initialize_output",toutput
        if 'type' not in toutput.config:
            toutput.config['type']='sp'
    
    def initialize_loop(self,tloop):
        print "eurotherm2000:initialize_loop",tloop
        
    def read_input(self, tinput):
        print "eurotherm2000:read_input",tinput.config['type']
        typ=tinput.config['type']
        if typ is 'op':
            return self._dev.op()
        elif typ is 'sp':
            return self._dev.get_setpoint()
        elif typ is 'wsp':
            return self._dev.get_setpoint(5)
        return self._dev.pv()
       
    def read_output(self, toutput):
        print "eurotherm2000:read_output",toutput.config['type']
        typ=toutput.config['type']
        if typ is 'wsp':
            return self._dev.get_setpoint(5)
        return self._dev.get_setpoint()
    
    def set(self, toutput, sp, **kwargs):
        print "eurotherm2000:set",sp, kwargs
        """
        Output type object only
        Send the command to go to a setpoint as quickly as possible
        Args:
           toutput:  Output class type object 
           sp:       setpoint
        Keyword Args:
           kwargs: auxilliary arguments
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        self._dev.setpoint(sp)
    
    def get_setpoint(self, toutput):
        print "eurotherm2000:get_setpoint"
        return self._dev.setpointvalue
        '''
        or
        print "eurotherm2000:get_setpoint",toutput.config['type']
        typ=toutput.config['type']
        if typ is 'wsp':
            return self._dev.get_setpoint(5)
        return self._dev.get_setpoint()
        '''
        
        """
        On Output type object only
        Return current setpoint
        Args:
           toutput:  Output class type object 
        Returns:
           (float) setpoint value. Must be None if not setpoint is set

        """


    def start_ramp(self, toutput, sp, **kwargs):
        """
        Output type object only
        Send the command to start ramping to a setpoint
        Args:
           toutput:  Output class type object 
           sp:       setpoint
        Keyword Args:
           kwargs: auxilliary arguments
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def set_ramprate(self, toutput, rate):
        """
        Output type object only
        Sets the ramp rate (for ramping mode)
        Args:
           toutput:  Output class type object 
           rate:     ramp rate
        Raises:
           NotImplementedError: when not defined by the inheriting class      
       """
        pass

    def read_ramprate(self, toutput):
        """
        Output type object only
        Reads the ramp rate (for ramping mode)
        Args:
           toutput:  Output class type object 
        Returns:
           ramp rate
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def set_dwell(self, toutput, dwell):
        """
        Output type object only
        Sets the dwell value (for step-ramping mode)
        Args:
           toutput:  Output class type object 
           dwell: dwell value (for step ramping)
        Raises:
           NotImplementedError: when not defined by the inheriting class      
       """
        pass
    
    def read_dwell(self, toutput):
        """
        Output type object only
        Reads the dwell value (for step-ramping mode)
        Args:
           toutput:  Output class type object 
        Returns:
           dwell value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def set_step(self, toutput, step):
        """
        Output type object only
        Sets the step value (for step-ramping mode)
        Args:
           toutput:  Output class type object 
           step: step value (for step ramping)
        Raises:
           NotImplementedError: when not defined by the inheriting class      
       """
        pass
    
    def read_step(self, toutput):
        """
        Output type object only
        Reads the dwell value (for step-ramping mode)
        Args:
           toutput:  Output class type object 
        Returns:
           step value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def set_kp(self, tloop, kp):
        """
        Loop type object only
        Sets the PID P value
        Args:
           tloop:  Loop class type object 
           kp: P value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def read_kp(self, tloop):
        """
        Loop type object only
        Reads the PID P value
        Args:
           tloop:  Loop class type object
        Returns:
           P value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def set_ki(self, tloop, ki):
        """
        Loop type object only
        Sets the PID I value
        Args:
           tloop:  Loop class type object 
           ki: I value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
       """
        pass
    
    def read_ki(self, tloop):
        """
        Loop type object only
        Reads the PID I value
        Args:
           tloop:  Loop class type object 
        Returns:
           I value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def set_kd(self, tloop, kd):
        """
        Loop type object only
        Sets the PID D value
        Args:
           tloop:  Loop class type object 
           kd: D value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
       """
        pass
    
    def read_kd(self, tloop):
        """
        Loop type object only
        Reads the PID D value
        Args:
           tloop:  Loop class type object 
        Returns:
           D value
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def state_input(self,tinput):
        print "eurotherm2000:state_input",tinput
        """
        Input type object only
        Return a string representing state of an Input object.
        Args:
           tinput:  Input class type object
        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """


    def state_output(self,toutput):
        """
        Output type object only
        Return a string representing state of an Output object.
        Args:
           toutput:  Output class type object
        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def setpoint_stop(self,toutput):
        """
        Output type object only
        Stops the setpoint
        Args:
           toutput:  Output class type object
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def setpoint_abort(self,toutput):
        """
        Output type object only
	    Aborts the setpoint (emergency stop)
        Args:
           toutput:  Output class type object
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def on(self,tloop):
        """
        Loop type object only
        Starts the regulation on the Loop class type object
        Args: 
           tloop:  Loop class type object
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def off(self,tloop):
        """
        Loop type object only
        Stops the regulation on the Loop class type object
        Args: 
           tloop:  Loop class type object
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def Wraw(self, str):
        """
        Callable from any type (Input/Output/Loop) class type object
        A string to write to the controller
        Args:
           str:  the string to write
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass

    def Rraw(self):
        """
        Callable from any type (Input/Output/Loop) class type object
        Reading the controller
        Returns:
           response from the controller
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
    def WRraw(self, str):
        """
        Callable from any type (Input/Output/Loop) class type object
        Write then Reading the controller
        Args:
           str:  the string to write
        Returns:
           response from the controller
        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """
        pass
    
