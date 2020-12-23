# Temperature framework

!!! info
    The Temperature framework is superseded by the [Regulation](regul_regulation_fw.md) framework.

    The Temperature framework is maintained until all controllers have been moved to the Regulation framework.

    The controllers still based on the Temperature framework are:

    - eurotherm2000
    - pace
    - meerstetter ltr1200


A generic python library to access temperature controllers in a uniform manner has been developed inside the BLISS framework (plugin Temperature).
It allows to manipulate objects such as Inputs/Outputs/Loops:

* Inputs objects allow to read sensors ;
* Outputs objects allow to read, do setpoints on heaters ;
* Loops objects allow to program the regulation loops in the controllers.

These objects will access the class written by the Temperature controller developer for the equipment (inheriting from the temperature Controller class).
This class has pre-defined method names that must be filled. Other methods or attributes (custom methods or attributes) can be freely defined by the developer.
Furthermore, a Tango access can be generated automatically to these objects. 


## Configuration
```yml

- class: mockup               <- mandatory
  plugin: temperature         <- mandatory (or in  __init__.yml, same folder)
  host: lid269
  inputs:
    - name: thermo_sample     <- mandatory
  outputs:
    - name: heater            <- mandatory
      low_limit: 10           <- recommended (default: None)
      high_limit: 200         <- recommended (default: None)
      deadband: 0.1           <- recommended (default: None)

  ctrl_loops:
    - name: sample_regulation <- mandatory
      input: $thermo_sample   <- mandatory
      output: $heater         <- mandatory
```

## Usage

The temperature controller is not directly used, instead users interact with the Loop object.

```python
TEST_SESSION [1]: sample_regulation
         Out [1]: <bliss.common.temperature.Loop object at 0x7f14de2d6990>
TEST_SESSION [11]: sample_regulation.on()  
Mockup: regulation on
TEST_SESSION [12]: sample_regulation.ramp(10)
TEST_SESSION [13]: sample_regulation.output.deadband
         Out [13]: 0.1
```


## Input class

The `Input` object inherits from `SamplingCounterController` and has one counter associated to the read method.

- `Input.controller`: returns the associated temperature controller
- `Input.state`: returns the sensor state
- `Input.read`: returns the sensor value

## Output class

The `Output` object inherits from `SamplingCounterController` and has one counter associated to the read method.

- `Output.controller`: returns the associated temperature controller
- `Output.limits`: returns the limits for the heater temperature setting
- `Output.deadband`: returns the deadband acceptable for the heater temperature setting
- `Output.read`: returns the heater value
- `Output.ramp`: starts a ramp on an output
- `Output.ramprate`: set/get the setpoint ramp rate value
- `Output.rampstate`: returns the setpoint state
- `Output.set`: sets as quickly as possible a temperature
- `Output.wait`: waits on a setpoint task
- `Output.stop`: stops a setpoint task and calls the controller stop method
- `Output.abort`: aborts a setpoint task and calls the controller abort method
- `Output.state`: returns the the state of a heater
- `Output.pollramp`: set/get the polling time (s) while waiting to reach setpoint
- `Output.step`: set/get the setpoint step value for step mode ramping
- `Output.dwell`: set/get the setpoint dwell value for step mode ramping

After a ramp or a set, the setpoint is considered to be reached only if heater value is within the deadband.

While the setpoint is not reached, a wait will block on it

  

## Loop class

The `Loop` object inherits from `SamplingCounterController` and has 2 counters (the counters associated to its input and output).

- `Loop.controller`: returns the temperature controller
- `Loop.name`: returns the loop name
- `Loop.input`: returns the loop input object
- `Loop.output`: returns the loop output object
- `Loop.set`: same as `Loop.output.set`
- `Loop.ramp`: same as `Loop.output.ramp`
- `Loop.stop`: same as `Loop.output.stop`
- `Loop.on`: sets the regulation on
- `Loop.off`: sets the regulation off
- `Loop.kp`: set/get the PID 'proportional' coefficient
- `Loop.ki`: set/get the PID 'integral' coefficient
- `Loop.kd`: set/get the PID 'derivative' coefficient


## Temperature Controller Base class

A custom controller class must inherit from the Temperature Controller class: 

`from bliss.controllers.temp import Controller`

The `Controller` class has pre-defined methods that must be filled. Other methods or attributes (custom methods or attributes) can be freely defined by the developer.

```python

class Controller:
    """
    Temperature controller base class
    """

    @property
    def name(self):

    @property
    def config(self):

    @property
    def inputs(self):

    @property
    def outputs(self):

    @property
    def loops(self):

    def initialize_hardware(self):

    def initialize(self):

    def initialize_input_hardware(self, tinput):

    def initialize_input(self, tinput):

    def initialize_output_hardware(self, toutput):

    def initialize_output(self, toutput):

    def initialize_loop_hardware(self, tloop):

    def initialize_loop(self, tloop):

    def read_input(self, tinput):

    def read_output(self, toutput):

    def start_ramp(self, toutput, sp, **kwargs):

    def set_ramprate(self, toutput, rate):

    def read_ramprate(self, toutput):

    def set_dwell(self, toutput, dwell):

    def read_dwell(self, toutput):

    def set_step(self, toutput, step):

    def read_step(self, toutput):

    def set_kp(self, tloop, kp):

    def read_kp(self, tloop):

    def set_ki(self, tloop, ki):

    def read_ki(self, tloop):

    def set_kd(self, tloop, kd):

    def read_kd(self, tloop):

    def set(self, toutput, sp, **kwargs):

    def get_setpoint(self, toutput):

    def state_input(self, tinput):

    def state_output(self, toutput):

    def setpoint_stop(self, toutput):

    def setpoint_abort(self, toutput):

    def on(self, tloop):

    def off(self, tloop):

```