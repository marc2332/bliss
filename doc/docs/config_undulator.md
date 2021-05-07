# Undulators

BLISS has a motor controller exporting axes from ESRF insertion devices.

* `ds_name` has to be the fully qualified name of the corresponding Tango server.
* `period`: period in mm of the undulator. Read from config (Usually the number
  in undulator name)
* `alpha`: alpha is a magic parameter used for undulator calibration. Read from
  config (To be set by BL staff or undulator group member)

For each axis, the corresponding Tango attribute names for position,
velocity and acceleration have to be specified.

!!!note
    `ESRF_Undulator` controller is a `NoSettingsAxis`, i.e. the parameters
    like velocity, accelerations are not configured in Beacon but read from Tango DS.

There are 2 ways to configure undulators axes:

* either giving the fulls names of the attributes:
```
        attribute_position: U42B_GAP_Position
        attribute_velocity: U42B_GAP_Velocity
        attribute_first_velocity: U42B_GAP_FirstVelocity
        attribute_acceleration: U42B_GAP_Acceleration
```
* or better give only the `undulator_prefix` (or `undu_prefix`):

```
         undulator_prefix: U42C_GAP_
```

## YAML configuration file example

In this example, the 2 types of configuration are used:

```yaml
- controller:
  class: ESRF_Undulator
  ds_name: //acs.esrf.fr:10000/id/master/id66
  axes:
      -
        name: u42b
        attribute_position: U42B_GAP_Position
        attribute_velocity: U42B_GAP_Velocity
        attribute_first_velocity: U42B_GAP_FirstVelocity
        attribute_acceleration: U42B_GAP_Acceleration
        steps_per_unit: 1
        tolerance: 0.1
        sign: 1
        low_limit: 0.01
        high_limit: 500
        period: 42
        alpha: 1.9206
      -
        name: u42c
        undulator_prefix: U42C_GAP_
        steps_per_unit: 1
        tolerance: 0.1
        low_limit: 0.01
        high_limit: 500
        period: 42
        alpha: 1.666
```


## information

`wid()` command gives info about all undulators configured in a session:

```
DEMO [1]: wid()

    ---------------------------------------
    ID Device Server //acs.esrf.fr:10000/id/master/id42
            Power: 0.000 /  10.0  KW
    Power density: 0.000 / 300.0  KW/mr2

    u42b - GAP:200.000 - ENABLED
    u42c - GAP:199.999 - ENABLED
    u32a - GAP:199.999 - ENABLED
```

Inline info provides detailed information about undulator axis:
```
u42b
AXIS:
     name (R): u42b
     unit (R): None
     offset (R): 0.00000
     backlash (R): 0.00000
     sign (R): 1
     steps_per_unit (R): 1.00
     tolerance (R) (to check pos. before a move): 0.1
     limits (RW):    Low: 0.01000 High: 500.00000
                     (config Low: 0.01000 High: 500.00000)
     dial (RW): 200.00213
     position (RW): 200.00213
     state (R): READY (Axis is READY)
     acceleration: None
     velocity: None
UNDU DEVICE SERVER: //acs.esrf.fr:10000/id/master/id42
     status = All undulator axis are ready to move
     state = ON
     Power = 0.239 (max: 3)
     PowerDensity = 6.2  (max: 30)
TANGO DEVICE SERVER VALUES:
     U42B_GAP_Position = 16.009625 mm
     U42B_GAP_Velocity = 5.0 mm/s
     U42B_GAP_FirstVelocity = 0.166 mm/s
     U42B_GAP_Acceleration = 0.166 mm/s/s
UNDU SPECIFIC INFO:
     config alpha: 1.9206
     config period: 42.0
ENCODER:
     None
```
