#BLISS Temperature controller

A generic python library to access temperature controllers in a uniform manner has been developed inside the BLISS framework (plugin Temperature).
It allows to manipulate objects such as Inputs/Outputs/Loops:

* Inputs objects allow to read sensors ;
* Outputs objects allow to read, do setpoints on heaters ;
* Loops objects allow to program the regulation loops in the controllers.

These objects will access the class written by the Temperature controller developer for the equipment (inheriting from the temperature Controller class).
This class has pre-defined method names that must be filled. Other methods or attributes (custom methods or attributes) can be freely defined by the developer.
Furthermore, a Tango access can be generated automatically to these objects. 



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
