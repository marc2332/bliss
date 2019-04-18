## Configuring an Elmo motor controller of the Whistle series from 2006 

This chapter explains how to configure an Elmo  whistle motor controller.

### Supported features

Encoder | Shutter | Trajectories 
------- | ------- | ------------ 
Yes	| NO      | NO          

The controller supports the search of hardware limits, homing and jogging features.
Three different user modes are possible:
* user_mode = 4: Used for linear movements. This mode uses the auxillary encoder feedback loop.
* user_mode = 5: Used for rotational movements. This mode uses the main encoder feedback loop.
* user_mode = 2: Speed control mode. This mode regulates the motors speed and not the motor position. In this mode 
                 no position control is possible.
                 The jogging functionality sets the controller in this mode and sets it back to position control 
                 when the jogging is stopped. 

### Specific Elmo controller parameters

* **url**: Serial line to be used
* **user_mode**: One of the user modes described above


### YAML configuration file example

```YAML
- name: MR_SZ
  class: Elmo_whistle
  serial:
    url: tango://id19/serialrp_192/22
  axes:
    - name: mrsz
      steps_per_unit: 2000 
      velocity: 10      # mm/s
      acceleration: 5   # mm/s2
      user_mode: 4
      
- name: MR_SROT
  class: Elmo_whistle
  serial:
    url: tango://id19/serialrp_192/20
  axes:
    - name: mrsrot
      steps_per_unit: 12800 
      velocity: 22.5    # deg/s
      acceleration: 45  # deg/s2
      user_mode: 5 
```
