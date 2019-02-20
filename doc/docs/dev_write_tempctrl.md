# Support of a new temperature controller

Temperature controller in BLISS inherit the *Controller* class from `bliss/controllers/temp.py`.


The file `TempControllerSkeleton.py` in `bliss/controllers/temperature` is a skeleton for writing a new temperature controller called *MyTemperatureController*.


1- A beacon configuration *YAML* file has to be defined.
   This file will define :
   
   - 'inputs'    : the list of Input type objects for this controller ;
   
   - 'outputs'   : the list of Output type objects for this controller ;
   
   - 'ctrl_loops': the list of Loop type objects for this controller.

   Following, an example is given, providing:
   
   - 2 Inputs type  objects: used for reading only. can be seen as sensors ;
   
   - 1 Output type object : reading, ramping can be performed on such object. Can be seen as heater ;
   
   - 1 Loop object        : to perform a regulation between an Input type object and an Output type object.

   Below, it is shown what is *mandatory*, what is *recommended*,
   and what is needed if you want a *Tango server control*.
   
   - mandatory:
   
      - *name*: for all objects, a *name* is mandatory ;
          
      - *input*/*output*: For a *loops* object only. You must provide the names of the
                            *inputs* object and *outputs* object used for the regulation.

   - recommended for the *outputs* objects :
   
      - *low_limit*/*high_limit*: you can provide these values if you need a filtering
            of the setpoints that you will send on you object. A *RunTimeError* with a
            message will be sent if you try to setpoint outside these limits ;
            
      - *deadband*: when you ramp to a setpoint, it allows to know when you have
            readched the setpoint (inside this deadband), using the *rampstate* method.

   - Tango server generation:
   
      - *tango_server*: name of the server generation.
                            In the following example, it will be generating when running it as:
                                     ```BlissTempManager temp1```

   Then, you can add any property you will need in you own YAML file:

```yaml
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
```


2- In the following skeleton *MyTemperatureController* class, the methods
   that must be written are documented.
   It can be noted also the following things:

   - Most of the methods receive as an argument the object from which they
   are called (name *tinput*, *toutput* and *tloop*).
   
   - A dictionnary has been defined for all these objects, in which it is
   easy for a TempController writer to store any useful data concerning one
   specific object:
     
     - tinput._attr_dict
         
     - toutput._attr_dict
         
     - tloop._attr_dict
         
   - These dictionnaries can be used freely by a TempController writer. As they
   are visible from the outside world, the '_' has been used in front of the name
   to protect its use, and to mention to a final client of a controller not to try 
   to use them...
 