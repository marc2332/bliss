
# Encoder

An encoder (`bliss.common.encoder.Encoder` object) can be defined on its own and
used standalone, or can be associated to an axis to perform some extra actions
before or after a movement.



## Encoder associated to an Axis


### Configuration

An encoder associated to an Axis is defined in `controller` section
and referenced in `axes` section.


```yaml
controller:
  class: icepap
  host: iceid42
  axes:
      - name: m4mot
        address: 1
        steps_per_unit: 817
        velocity: 0.3
        acceleration: 3
        tolerance: 0.001
        encoder: $m4enc
        check_encoder: True
        read_position: encoder
  encoders:
      - name: m4enc
        address: 25
        steps_per_unit: 1e5
        tolerance: 0.02
```


Configuration parameters:

* `name`
    - Encoder object's name.
* `steps_per_unit`
    - This value is used to define the conversion factor between
    encoder steps value and real position in user unit. It must be
    accurate to allow comparison between position required by user and
    real position.
* `tolerance`
    - Value in **user_units**.
    - At end of a movement, the encoder value is read and compared to
    the target position of the movement. If the difference is outside
    the limit fixed by the **encoder tolerance** (beware to not
    confuse with Axis tolerance), an exception is raised with message:
    `"didn't reach final position"`
* `address`
    - specific for [icepap encoder](config_icepap.md#encoder-configuration).

!!! note
    For specific details about icepap encoders, see
    [Icepap Encoder Configuration](config_icepap.md#encoder-configuration)

### Usage

* the method `.measured_position()` uses `encoder.read()` to calculate
  the value returned *in user units*.

* if Axis parmeter `check_encoder` is set to `True`, then *after* a movement,
  the encoder position is read and compared to the target position. In case of
  difference outside the limit fixed by **Encoder tolerance**, an exception is
  raised with message: `"didn't reach final position"`

  The Axis must then be re-synchronized with:
  `mot1.sync_hard()`

* if Axis parmeter `read_position` is set to `encoder`, then the hardware
  position returned by the axis is the position read by the encoder like
  `.measured_position()`. This option disables the **discrepancy check** at the
  beginning of a movement unless `check_encoder` is also set to `True`.

!!! note
    This configuration (`read_position` is set to `encoder`) corresponds
    to the MAXE_E MAXEE mode in SPEC.

!!! note
    This `measured_position()` method is used in particular by
    TangoDS and can be easily compared to the target position with
    atk-moni for tuning purposes.

* `dial_measured_position()` returns the dial encoder position *in
  user units*.



!!! note
    There are 2 `tolerance` parameters in configuration: one for
    `Axis` and the other one for `Encoder`.



An encoder can be used to define events to trig on special positions.
See: [Writing a motor controller -
position-triggers](dev_write_motctrl.md#position-triggers)



## Standalone encoder


```
controller:
  class: icepap
  host: iceid42
  encoders:
      - name: m4enc
        address: 25
        steps_per_unit: 1e5
```


## Encoder as a counter

It is possible to use an encoder alone to read it or to scan/count it.

```python
DEMO [9]: samy.encoder
 Out [9]: ENCODER:
               tolerance (to check pos at end of move): 0.001
               dial_measured_position:    7.39992
```

```python
DEMO [13]:
DEMO [13]: ct(1, samy.encoder)
Fri Feb 07 11:53:15 2020

position = 7.399929 ( 7.399929 /s)
  Out [13]: Scan(number=4, name=ct, path=)
```



## development

For details on how to implement an encoder in a new motor controller,
see [Writing a motor controller / Encoder
methods](dev_write_motctrl.md#encoder-methods)

