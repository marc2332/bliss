#BLISS Temperature controller

A generic python library to access temperature controllers in a uniform manner has been developed inside the BLISS framework.
Acutally, at the moment, two plugins are cohabihing:

* Old plugin Temperature ;
* new plugin Regulation.

It allows to manipulate objects such as Inputs/Outputs/Loops:

* Inputs objects allow to read sensors ;
* Outputs objects allow to read, do setpoints on heaters ;
* Loops objects allow to program the regulation loops in the controllers.

These objects will access the class written by the Temperature controller developer for the equipment (inheriting from the temperature Controller class).
This class has pre-defined method names that must be filled. Other methods or attributes (custom methods or attributes) can be freely defined by the developer.
Furthermore, a Tango access can be generated automatically to these objects.


##New regulation plugin:

This module implements the classes allowing the control of regulation processes and associated hardware

The regulation is a process that:

1. reads a value from an input device 
2. takes a target value (setpoint) and compare it to the current input value (processed value)
3. computes an output value sent to an output device which has an effect on the processed value
4. back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

The regulation Loop has:

* one input: an Input object to read the processed value (ex: temperature sensor)
* one output: an Output object which has an effect on the processed value (ex: cooling device)

The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
The Loop object implements methods to manage the PID algorithm that performs the regulation.
A Loop object is associated to one Input and one Output.

The Loop object has a ramp object. If loop.ramprate != 0 then any new setpoint cmd (using Loop.setpoint)
will use a ramp to reach that value (HW ramp if available else a 'SoftRamp').

The Output object has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output
will use a ramp to reach that value (HW ramp if available else a 'SoftRamp').
    
Depending on the hardware capabilities we can distinguish two main cases.

1) Hardware regulation:

   A physical controller exists and the input and output devices are connected to the controller.
   In that case, a regulation Controller object must be implemented by inheriting from the Controller base class (bliss.controllers.regulator).
   The inputs and ouputs attached to that controller are defined through the YML configuration file.

```
---------------------------- YML file example ---------------------------------    

            -
                class: Mockup                  # <-- the controller class inheriting from 'bliss.controllers.regulator.Controller'
                module: temperature.mockup # or powersupply.mockup
                host: lid42
                inputs:
                    - 
                        name: thermo_sample
                        channel: A
                        unit: deg

                    - 
                        name: sensor
                        channel: B
            
                outputs: 
                    -
                        name: heater
                        channel: A 
                        unit: Volt
                        low_limit:  0.0          # <-- minimum device value [unit] 
                        high_limit: 100.0        # <-- maximum device value [unit]
                        ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
            
                ctrl_loops:
                    -
                        name: sample_regulation
                        input: $thermo_sample
                        output: $heater
                        P: 0.5
                        I: 0.2
                        D: 0.0
                        low_limit: 0.0           # <-- low limit of the PID output value. Usaually equal to 0 or -1.
                        high_limit: 1.0          # <-- high limit of the PID output value. Usaually equal to 1.
                        frequency: 10.0
                        deadband: 0.05
                        deadband_time: 1.5
                        ramprate: 1.0            # <-- ramprate to reach the setpoint value [input_unit/s]
                        wait_mode: deadband
             
            -------------------------------------------------------------------
            
```
2) Software regulation

   Input and Output devices are not always connected to a regulation controller.
   For example, it may be necessary to regulate a temperature by moving a cryostream on a stage (axis).
   Any 'SamplingCounter' can be interfaced as an input (ExternalInput) and any 'Axis' as an input or output (ExternalOutput).
   Devices which are not standard Bliss objects can be interfaced by implementing a custom input or output class inheriting from the Input/Output classes.

   To perform the regulation with this kind of inputs/outputs not attached to an hardware regulation controller, users must define a SoftLoop.
   The SoftLoop object inherits from the Loop class and implements its own PID algorithm (using the 'simple_pid' Python module).
        
```
                -----------------YML file example -----------------------------

            -   
                class: MyCustomInput     # <-- a custom input defined by the user and inheriting from the ExternalInput class
                package: bliss.controllers.regulation.temperature.mockup  # <-- the module where the custom class is defined
                plugin: bliss
                name: custom_input
                unit: eV
                        
            
            -   
                class: MyCustomOutput    # <-- a custom output defined by the user and inheriting from the ExternalOutput class
                package: bliss.controllers.regulation.temperature.mockup  # <-- the module where the custom class is defined
                plugin: bliss
                name: custom_output
                unit: eV
                low_limit: 0.0           # <-- minimum device value [unit]
                high_limit: 100.0        # <-- maximum device value [unit]
                ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
            
            
            - 
                class: Input             # <-- value of key 'class' could be 'Input' or 'ExternalInput', the object will be an ExternalInput
                name: diode_input          
                device: $diode           # <-- a SamplingCounter
                unit: mm
            
            
            -
                class: Output            # <-- value of key 'class' could be 'Output' or 'ExternalOutput', the object will be an ExternalOutput
                name: robz_output        
                device: $robz            # <-- an axis
                unit: mm
                low_limit: 0.0           # <-- minimum device value [unit]
                high_limit: 100.0        # <-- minimum device value [unit]
                ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
                
            
            - 
                class: Loop              # <-- value of key 'class' could be 'Loop' or 'SoftLoop', the object will be a SoftLoop
                name: soft_regul
                input: $custom_input
                output: $robz_output
                P: 0.5
                I: 0.2
                D: 0.0
                low_limit: 0.0            # <-- low limit of the PID output value. Usaually equal to 0 or -1.
                high_limit: 1.0           # <-- high limit of the PID output value. Usaually equal to 1.
                frequency: 10.0
                deadband: 0.05
                deadband_time: 1.5
                ramprate: 1.0       

                ----------------------------------------------------------------
```
    
Note: a SoftLoop can use an Input or Output defined in a regulation controller section.
For example the 'soft_regul' loop could define 'thermo_sample' as its input.  


*The following appliances are ready for this new regulation plugin*:

*    Lakeshore : 331, 332, 335, 336, 340 ;
*    Linkam: TMS94, T95 ;
*    NHQ power supplies model: 102M 103M 104M 105M 106L 202M 203M 204M 205M 206L ;
*    ACE: ESRF Avalanche Photo-diode in direct counting ;
*    Oxford Cybertar: X1000, X2000, 5 channels.



## Old plugin Temperature

Old examples for the lakeshore are now not used but are still some examples for this controllers:
* Eurotherm
* Oxford cryostat controllers
* Meerstetter

#YAML file

This YAML file allows to configure a particular equipment. Here below is an example for a Lakeshore 336.
It defines 2 Input objects, 2 outputs object, 2 loops object.
```yaml
#controller:
- class: lakeshore336             <- mandatory
  module: lakeshore.lakeshore336  <- mandatory
  name: lakeshore336              <- mandatory
  timeout: 3                      <- mandatory
  tcp:                            <- mandatory
     url: lakeshore336se2:7777    <- mandatory

  inputs:
    - name: ls336_A               <- mandatory
      channel: A                  <- mandatory
      unit: Kelvin                <- mandatory
    - name: ls336_A_c             <- mandatory  
      channel: A                  <- mandatory
      unit: Celsius               <- mandatory 
    - name: ls336_A_su            <- mandatory
      channel: A                  <- mandatory
      unit: Sensor_unit           <- mandatory

    - name: ls336_B               <- mandatory
      channel: B                  <- mandatory
      unit: Kelvin                <- mandatory
    - name: ls336_B_c             <- mandatory
      channel: B                  <- mandatory
      unit: Celsius               <- mandatory
    - name: ls336_B_su            <- mandatory
      channel: B                  <- mandatory
      unit: Sensor_unit           <- mandatory
      #tango_server: temp1        <- for Tango server, not used in this case     

  outputs:
    - name: ls336o_1              <- mandatory
      channel: 1                  <- mandatory
      unit: Kelvin                <- mandatory
    - name: ls336o_2              <- mandatory
      channel: 2                  <- mandatory
      unit: Kelvin                <- mandatory
      low_limit: 10               <- recommended
      high_limit: 200             <- recommended
      deadband: 0.1               <- recommended
      #tango_server: temp1        <- for Tango server, not used in this case
      
  ctrl_loops:
    - name: ls336l_1              <- mandatory
      input: $ls336_A             <- mandatory
      output: $ls336o_1           <- mandatory
      channel: 1                  <- mandatory
    - name: ls336l_2              <- mandatory
      input: $ls336_B             <- mandatory
      output: $ls336o_2           <- mandatory
      channel: 2                  <- mandatory 
      #tango_server: temp1        <- for Tango server, not used in this case
```      
For output objects, low_limit, high_limit and deadband are recommended. They allow to filter setpoints outside a range, and to define the condition when a setpoint is supposed to be reached.
The *unit* select the reading for the inputs and the *setpoint* *unit* in the outputs.



#API client

Based on this YAML file, the access and manipulation of the Lakeshore 336 objects (and generalisable to any temperature controller) will be:

* input=config.get("ls336_A") ;

* output=config.get("ls336o_1") ;

* loop=config.get("ls336l_1").

```yaml
#----------------- Input object
                   ## properties
input.controller   <bliss.controllers.temperature.lakeshore.lakesore at 0x1fb2a90>
input.config	   filename:<controllers/temperature/lakeshore/lakeshore336.yml>,
                   plugin:'temperature',
                   {'name': 'ls336_A', 'unit': 'Kelvin', 'channel': 'A'}
input.config.get("channel",str)    'A'
input.name	  'ls336_A

                   ## methods
input.state()		'READY'
input.read()		-4.0272488397569868

                       ## custom attribute
input.set_material("CH4OH") 	
input.get_material()	'CH40H'

                       ## custom command
input.get_double_str("calor") 'calor_calor'


#----------------- Output object
                   ## properties
output.controller
output.name		'heatls336o_1er'
output.config
output.limits		(10, 200)
output.deadband		0.10000000000000001

                       ## methods
output.read()		-4.0272488397569868
output.state()		'READY'

output.ramprate(45)
output.ramprate()	45
output.step(23)
output.step()		23
output.dwell(2)
output.dwell()		2

output.ramp(10)		
output.ramp(10,True)        # by default, wait=False
output.ramp(10,ramp=3 ...)  # with custom kwargs
output.set(2)
output.ramp()		10  # returns the setpoint (whatever the mode ramp/direct)
output.set()		2   # returns the setpoint
output.rampstate()	RUNNING or READY
output.stop()
output.abort()
output.wait()

output.pollramp(1)	    # set polling time for setpoint reached
output.pollramp()	    # returns polling time		

output.controller.Rraw()
output.controller.Wraw("Hello!!!")
output.controller.WRraw("Hello!!!")

#---------------- Loop object
                       ## properties
loop.name		'sample_regulation'
loop.controller()
loop.config()
loop.input
loop.output

loop.input.read()	-4.0272488397569868
...
loop.output.read()      11
...

                       ## methods
loop.ramp(15)          # same as loop.output.ramp(15)
loop.set(18)           # same as loop.output.set(18)
loop.stop()            # same as loop.output.stop()

loop.on()
loop.off()
loop.kp(10)            # PID: P
loop.kp()
loop.ki(12)            # PID: I
loop.ki()
loop.kd(2)             # PID: D
loop.kd()
```



#Counters

For scanning in the bliss environment, the Input/Output objects temperature values can be accesses through their *counter* CounterBase object.

`print bb.counter.read()`
