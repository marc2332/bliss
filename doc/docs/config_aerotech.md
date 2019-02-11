## Configuring an Aerotech motor controller

This chapter explains how to configure an Aerotech motor controller.

For now is only tested on **Ensemble** controllers.

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
YES	| NO      | NO          

### Specific Aerotech axis parameters

* **aero_name**: axis name is the channel name set in the controller

### YAML configuration file example

```YAML
- class: aerotech
  tcp:
    url: id15aero1
    #url: 172.24.168.121
  axes:
    - name: rot
      aero_name: X
      steps_per_unit: 67356.444444444
      velocity: 10.0
      acceleration: 25.0
      encoder: rot_enc
      tolerance: 1e-3
```
### Encoder configuration

Encoders directly plugged in the Aerotech controller can be configured directly
in the YAML configuration file.

#### Specific Aerotech encoder parameters

* **aero_name**:  axis name is the channel name set in the controller

#### Encoder YAML configuration example

```YAML
- class: aerotech
  tcp:
    url: id15aero1
  encoders:
    - name: rot_enc
      aero_name: X
```
