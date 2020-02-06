# Configuring a Wago Analog Output as a motor

## Wago Motor

This capability is given to be used inside scans where you need to change the Wago output accordingly with the progression of the Scan itself.

To know how to configure a Wago read the section [Wago](config_wago.md)


## YAML configuration file example

```yaml
controller:
- module: wago
  class: WagoMotor
  wago: $wago_simulator
  axes:
  - name: dacm1
    logical_name: o10v1
    logical_channel: 0
    low_limit: 0
    high_limit: 10
    unit: V
  - name: dacm2
    logical_name: o10v2
    logical_channel: 0
    low_limit: 0
    high_limit: 10
    unit: V
```

Axes names should correspond to `logical_devices` configured in the
wago itself. If there are multiple channels defined with the same name be sure to specify also the `logical_channel`.


There is no need to specify `velocity`, `acceleration` as this does not make sense (changes of output are always made at the maximum speed).

In the current implementation it is not possible to specify `steps_per_unit`.
