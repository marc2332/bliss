# Interface for an actuator controller
It can be applied for any type of hardware, which requires a two state action
(set_in/set_out) and might couple the action with a test of achievement.

!!! warning
    The underlying controller should at least have a method `.set()` and if possible a method `.get()`.

### Example YAML configuration file ###
```yaml
   class: actuator
   name: detector_cover
   controller: $wcid29a
   actuator_cmd: detcover
   actuator_state_in: detcover_in
   actuator_state_out: detcover_out
   actuator_inout: {"in":0, "out":1}
```

The **controller** is Wago. The predefined tags correspond to:

*  *actuator_cmd*: the name of the control channel
*  *actuator_state_in* and/or *actuator_state_out*: names of channels, commected to the limit switches
*  *actuator_inout*: values to set 0 or 1

```yaml
   class: actuator
   name: capillary
   controller: $diffractometer
   actuator_cmd: CapillaryPosition
   actuator_state_in: CapillaryPosition
   actuator_state_out: CapillaryPosition
   actuator_inout: {"in": "ON", "out": "OFF"}
```

The **controller** is MD2S. The predefined tags correspond to:

*  *actuator_cmd*: command to set the actuator
*  *actuator_state_in* and *actuator_state_out*: commands to read the status
*  *actuator_inout*: values to set ON and OFF

The plugin for this controller is `bliss`:
```yaml
   plugin: bliss
```
should either be in \_\_init__.yml in the same directory or added to the above configuration.
