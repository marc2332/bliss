## Configuring an Galil motor controller

This chapter explains how to configure an Galil motor controller.

### Supported features

Encoder | Shutter | Trajectories 
------- | ------- | ------------ 
NO	| NO      | NO          

### Specific Galil controller parameters

* **url**: controller hostname or IP address

### Specific IcePAP axis parameters

* **type**: is the motor type, default value is SERVO == 1. Values could be:
  * 1 : Servo Motor
  * -1 : Servo motor with reversed polarity
  * -2 : Step motor with active high step pulses
  * 2 : Step motor with active low step pulses
  * -2.5: Step motor with reversed direction and active high step pulses
  * 2.5: Step motor with reversed direction and active low step pulses
* **vect_acceleration**: acceleration rate of the vector in a coordinated motion sequence. default value is 262144
* **vect_deceleration**: deceleration rate of the vector in a coordinated motion sequence. default value is 262144
* **vect_slewrate**: speed of the vector in a coordinated motion sequence. default value is 8192
* **encoder_type**: the quadrature type or the pulse and direction type. default value is QUADRA == 0. Values can be:
  * 0: Normal quadrature
  * 1: Normal pulse and direction
  * 2: Reversed quadrature
  * 3: Reversed pulse and direction
* **kp**: Proportional Constant. default value is 1.0
* **ki**: Integrator. default value is 6.0
* **kd**: Derivative Constant. default value is 7.0
* **integrator_limit**: limits the effect of the integrator function in the filter to a certain voltage.
For example, integrator_limit 2 limits the output of the integrator of the A-axis to the +/-2 Volt range.
default value is set to the maximum value (9.998)
* **smoothing**: Independent Time Constant. default value is 1.0
* **error_limit**: the magnitude of the position errors for each axis that will trigger an
error condition. default value is 16384
* **cmd_offset**: bias voltage in the motor command output. default value is 0.0
* **torque_limit**: the limit on the motor command output. For example, torque_limit of 5 limits
the motor command output to 5 volts. Maximum output of the motor command is 9.998
volts. default value is set to the maximum.

### YAML configuration file example

```YAML
 - class: GalilDMC213
   tcp:
     url: galildevice
   axes:
    - name: phi
      steps_per_unit: 26222.2
      velocity: 14.4
      acceleration: 28.8
      unit: deg
```