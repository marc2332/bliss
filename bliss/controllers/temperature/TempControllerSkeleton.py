# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""

This is a skeleton for writing a temperature controller called MyTemperatureController

1- A beacon .yml file has to be defined.
   Here, an example is given, providing 
   - 2 'inputs' objects: used for reading only. can be seen as sensors.
   - 1 'outputs' object: reading, ramping can be performed on such object. 
                         can be seen as heater
   - 1 'loops object   : to perform a regulation between an 'inputs' object
                         and an 'outputs' object

   In this example, it is shown also what is 'mandatory', what is 'recommended'
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


""" TempController import """
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop
from bliss.common import log
from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set


class MyTemperatureController(Controller):

    def __init__(self, config, *args):
        """ 
        controller configuration
        """
        Controller.__init__(self, config, *args)


    def initialize(self):
        """ 
        Initializes the controller. not mandatory 
        """


    def initialize_input(self,tinput):
        """
        Initializes an Input class type object
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Input

        Args:
           tinput:  Input class type object          
        """
 

    def initialize_output(self,toutput):
        """
        Initializes an Output class type object
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object          
        """
 
    def initialize_loop(self,tloop):
        """
        Initializes a Loop class type object
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object          
        """

    def read_input(self, tinput):
        """
        Reads an Input class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        MANDATORY if Input

        Returns:
           read value         
        """


    def read_output(self, toutput):
        """
        Reads an Onput class type object
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 

        Returns:
           read value         
        """


    def start_ramp(self, toutput, sp, **kwargs):
        """
        Send the command to start ramping to a setpoint
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
           sp:       setpoint
           **kwargs: auxilliary arguments
        """


    def set_ramprate(self, toutput, rate):
        """
        Sets the ramp rate
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
           rate:     ramp rate
       """


    def read_ramprate(self, toutput):
        """
        Reads the ramp rate
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
        
        Returns:
           ramp rate
        """


    def set_dwell(self, toutput, dwell):
        """
        Sets the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
           dwell
       """

    def read_dwell(self, toutput):
        """
        Reads the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
        
        Returns:
           dwell value
        """

    def set_step(self, toutput, step):
        """
        Sets the step value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
           step
       """

    def read_step(self, toutput):
        """
        Reads the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
        
        Returns:
           step value
        """


    def set_kp(self, tloop, kp):
        """
        Sets the PID P value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
           kp
        """


    def read_kp(self, tloop):
        """
        Reads the PID P value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """


    def set_ki(self, tloop, ki):
        """
        Sets the PID I value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
           ki
       """

    def read_ki(self, tloop):
        """
        Reads the PID I value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """

    def set_kd(self, tloop, kd):
        """
        Sets the PID D value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
           kd
       """

    def read_kd(self, tloop):
        """
        Reads the PID D value
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kd value
        """


    def set(self, toutput, sp, **kwargs):
        """
        Send the command to go to a setpoint as quickly as possible
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 
           sp:       setpoint
           **kwargs: auxilliary arguments
        """

    def get_setpoint(self, toutput):
        """
        Return current setpoint
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object 

        Returns:
           (float) setpoint value. Must be None if not setpoint is set
        """


    def state_input(self,tinput):
        """
        Return a string representing state of an 'inputs' object.
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Input

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """


    def state_output(self,toutput):
        """
        Return a string representing state of an 'outputs' object.
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """

    def setpoint_stop(self,toutput):
        """
        Stops the setpoint
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object
        """


    def setpoint_abort(self,toutput):
        """
	    Aborts the setpoint (emergency stop)
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Output

        Args:
           toutput:  Output class type object
        """


    def on(self,tloop):
        """
        Starts the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args: 
           tloop:  Loop class type object
        """

    def off(self,tloop):
        """
        Stops the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY if Loop

        Args: 
           tloop:  Loop class type object
        """


    def Wraw(self, str):
        """
        A string to write to the controller
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY 

        Args:
           str:  the string to write
        """


    def Rraw(self):
        """
        Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY

        returns:
           response from the controller
        """

    def WRraw(self, str):
        """
        Write then Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        MANDATORY 

        Args:
           str:  the string to write
        returns:
           response from the controller
        """


 
#              ---- Example of custom commands ----
# It will be possible to access it as a command through generated device server
        

# Custom Command for all the objects types (Input/Output/Loop)
    @object_method(types_info=("str", "str"))
    def mymethodname(self, tobj, value):
        """
        Definition of a custom method. 

        Args:
           tobj: is the tinput/toutput/tloop object
           value: the argument in case it takes one. it must match
                  the types_info input argument type
        returns:
           return value type must match the 'types_info' return value type

        @object_method_type arguments:
           - types_info: tuple of data types accordind to PyTango definitions
                         for input argument and output argument
                         some examples:
                            ("None","str")    : returns a value
                            ("float","float") : get a float and returns a float
        """

# Custom Command for Input, Output or Loop type only
    @object_method_type(types_info=("str", "str"), type=Input)
    def mymethodname(self, tinput, value):
        """
        Definition of a custom method fitered for a specific object type
        (Input/Output/Loop).
        It will be possible to access it as a command through generated device server

        Args:
           tobj: is the tinput/toutput/tloop object
           value: the argument in case it takes one. it must match
                  the 'types_info' input argument type
        returns:
           return value type must match the 'types_info' return value type

        @object_method_type arguments:
           - types_info: tuple of data types accordind to PyTango definitions
                         for input argument and return value
                         some examples:
                            ("None","str")    : returns a string value
                            ("float","float") : get a float and returns a float
            - type: Input/Output/Loop to filter this custom command
                   to one particular object type

         """

#              ---- Example of custom attributes ----
# It will be possible to access it as an attribute through generated device server.
# For a Tango device server custom attribute named <myattribute>, you need to define
# get_<myattribute> and set_<myattribute> methods.


# Custom Attribute for all the objects types (Input/Output/Loop)
    @object_attribute_get(type_info=("str"))
    def get_myattribute(self, tobj):
        """
        Definition for a custom attribute reading method

        Args:
           tobj: is the tinput/toutput/tloop object

        returns:
           return value type must match the 'type_info' return value type

        @object_attribute_get argument:
           - type_info: tuple of data type accordind to PyTango definitions
                         for return value type

        """

    @object_attribute_set(type_info=("str"))
    def set_myattribute(self, tobj, value):
        """
        Definition for a custom attribute setting method

        Args:
           tobj: is the tinput/toutput/tloop object

           value: the input argument. it must match
                  the 'types_info' input argument type


        @object_attribute_set argument:
           - type_info: tuple of data type accordind to PyTango definitions
                         for input argument type

        """

    # Custom Attribute for Input Output or Loop type only
    @object_attribute_type_get(type_info=("str"), type=Input)
    def get_myattribute(self, tobj):
        """
        Definition for a custom attribute reading method 

        Args:
           tobj: is the tinput/toutput/tloop object

        returns:
           return value type must match the 'type_info' return value type

        @object_attribute_get argument:
           - type_info: tuple of data type accordind to PyTango definitions
                         for return value type
           - type: Input/Output/Loop to filter this custome attribute
                   to one particular object type

        """

    @object_attribute_type_set(type_info=("str"))
    def set_myattribute(self, tobj, value):
        """
        Definition for a custom attribute setting method

        Args:
           tobj: is the tinput/toutput/tloop object

           value: the input argument. it must match
                  the 'types_info' input argument type


        @object_attribute_set argument:
           - type_info: tuple of data type accordind to PyTango definitions
                         for input argument type
           - type: Input/Output/Loop to filter this custome attribute
                   to one particular object type

        """

