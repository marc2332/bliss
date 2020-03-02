# Undulators

BLISS has a motor controller exporting axes from ESRF insertion devices.

* `ds_name` has to be the fully qualified name of the corresponding Tango server.

* `period`: period in mm of the undulator. Read from config
* `alpha`: alpha is a magic parameter used for undulator calibration. Read from config

For each axis the corresponding Tango attribute names for position,
velocity and acceleration have to be specified.

There are 2 ways to do that:

* either giving the fulls names of the attributes:
```
        attribute_position: U42B_GAP_Position
        attribute_velocity: U42B_GAP_Velocity
        attribute_first_velocity: U42B_GAP_FirstVelocity
        attribute_acceleration: U42B_GAP_Acceleration
```
* or just giving the undu_prefix:

```
         undu_prefix: U42C_GAP_
```

## YAML configuration file example

In this example, the 2 types of configuration are used:

```yaml
- controller:
  class: ESRF_Undulator
  ds_name: //acs:10000/id/master/id66
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
        undu_prefix: U42C_GAP_
        steps_per_unit: 1
        tolerance: 0.1
        low_limit: 0.01
        high_limit: 500
        period: 42
        alpha: 1.666
```


## info

Example of non-initilized undulator:
```
DEMO  [4]: u42b
  Out [4]: AXIS:
                name (R): u42b
                unit (R): None
                offset (R): 0.00000
                backlash (R): 0.00000
                sign (R): 1
                steps_per_unit (R): 1.00
                tolerance (R) (to check pos. before a move): 0.1
                limits (RW):    Low: 0.01000 High: 500.00000    (config Low: 0.01000 High: 500.00000)
                dial (RW): 200.00213
                position (RW): 200.00213
                state (R): READY (Axis is READY)
                acceleration: None
                velocity: None
           UNDU DEVICE SERVER: //acs:10000/id/master/id42
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
