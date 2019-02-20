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
            of the setpoints that you will send on you object. A **RunTimeError** with a
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
        Initializes the controller.
        """

    def initialize_input(self, tinput):
        """
        Input type object only

        Initialize an Input class type object

        Args:
           tinput:  Input class type object 
        """

    def initialize_output(self, toutput):
        """
        Output type object only

        Initialize an Output class type object

        Args:
           toutput:  Output class type object          
        """

    def initialize_loop(self, tloop):
        """
        Loop type object only

        Initialize a Loop class type object

        Args:
           tloop:  Loop class type object          
        """

    def read_input(self, tinput):
        """
        Input type object only

        Reads an Input class type object

        Args:
           tinput:  Input class type object 

        Returns:
           read value         

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def read_output(self, toutput):
        """
        Output type object only

        Reads an Output class type object

        Args:
           toutput:  Output class type object 

        Returns:
           read value         

        Raises:
           NotImplementedError: when not defined by the inheriting class      
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

    def set(self, toutput, sp, **kwargs):
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

    def get_setpoint(self, toutput):
        """
        On Output type object only

        Return current setpoint

        Args:
           toutput:  Output class type object 

        Returns:
           (float) setpoint value. Must be None if not setpoint is set
        """

    def state_input(self, tinput):
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

    def state_output(self, toutput):
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

    def setpoint_stop(self, toutput):
        """
        Output type object only

        Stops the setpoint

        Args:
           toutput:  Output class type object

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def setpoint_abort(self, toutput):
        """
        Output type object only

	    Aborts the setpoint (emergency stop)

        Args:
           toutput:  Output class type object

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def on(self, tloop):
        """
        Loop type object only

        Starts the regulation on the Loop class type object

        Args: 
           tloop:  Loop class type object

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def off(self, tloop):
        """
        Loop type object only

        Stops the regulation on the Loop class type object

        Args: 
           tloop:  Loop class type object

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def Wraw(self, str):
        """
        Callable from any type (Input/Output/Loop) class type object

        A string to write to the controller

        Args:
           str:  the string to write

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

    def Rraw(self):
        """
        Callable from any type (Input/Output/Loop) class type object

        Reading the controller

        Returns:
           response from the controller

        Raises:
           NotImplementedError: when not defined by the inheriting class      
        """

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
