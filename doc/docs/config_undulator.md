# Undulators

BLISS has a motor controller exporting axes from ESRF insertion devices.

`ds_name` has to be the fully qualified name of the corresponding Tango server.

In addition to standard parameters like `velocity` or `acceleration`, for each axis
the corresponding Tango attribute names for position, velocity and acceleration have
to be specified.

## YAML configuration file example


```yaml
controller:
  class: ESRF_Undulator
  ds_name: //acs:10000/id/master/id23
  axes:
      -
        name: u23a
        attribute_position: U23A_GAP_Position
        attribute_velocity: U23A_GAP_Velocity
        attribute_acceleration: U23A_GAP_Acceleration
        steps_per_unit: 1000
        velocity: 5
        acceleration: 125
        tolerance: 0.1
```
