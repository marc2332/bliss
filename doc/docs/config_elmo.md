## Configuring an Elmo motor controller

This chapter explains how to configure an Elmo motor controller.

### Supported features

Encoder | Shutter | Trajectories 
------- | ------- | ------------ 
NO	| NO      | NO          

### Specific Elmo controller parameters

* **url**: controller hostname or IP address

### Specific IcePAP axis parameters

* **control_slave**: if a second axis follow this one

### YAML configuration file example

```YAML
 - class: elmo
   udp:
     url: nscopeelmo
   axes:
    - name: rot
      steps_per_unit: 26222.2
      velocity: 14.4
      acceleration: 28.8
      control_slave: True
      unit: deg
```