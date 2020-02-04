
# Encoder

An encoder (`bliss.common.encoder.Encoder` object) can be defined on
its own, or can be associated to an axis to add some extra checks
before and after a movement.

* For configuration, see: [Encoder Configuration](config_encoder.md)
* For specific details about icepap encoders, see
[Icepap Encoder Configuration](config_icepap.md#encoder-configuration)

!!! note
    There are 2 `tolerance` parameters in configuration: one for
    `Axis` and the other for `Encoder`.

If an encoder is associated to the axis:

* the method `measured_position()` uses `encoder.read()` to calculate
  the value returned *in user units*.

* and if `check_encoder` is set to `True` in config, *after* a
  movement, the encoder position is read and compared to the target
  position of the movement. In case of difference outside the limit
  fixed by **Encoder tolerance**, an exception is raised with message:
  `"didn't reach final position"`

!!! note
    This `measured_position()` method is used in particular by
    TangoDS and can be easily compared to the target position with
    atk-moni for tuning purposes.

* `dial_measured_position()` returns the dial encoder position *in
  user units*.


An encoder can be used to define events to trig on special positions.
See: [Writing a motor controller -
position-triggers](dev_write_motctrl.md#position-triggers)

## Encoder as a counter

A `SoftCounter` object can be defined to use an encoder as a BLISS counter in a
scan by putting in the setup of a BLISS session:

```python
from bliss.common.counter import SoftCounter

<counter> = SoftCounter(<encoder>, <function used to read>, name=<counter_name>)`
```

example:
```python
from bliss.common.counter import SoftCounter

hpz_enc = SoftCounter(hpzrotid16_enc, 'read', name='hpz_enc')
```

!!! note
    hpz_enc can be used in a measurement group, but do not add `"hpz_enc"`
    in the `config-objects` list of the BLISS session.


## development

For details on how to implement an encoder in a new motor controller,
see [Writing a motor controller / Encoder
methods](dev_write_motctrl.md#encoder-methods)

