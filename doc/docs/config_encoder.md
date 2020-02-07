
For encoder usage and info for developers, see: [Encoder
Usage](motion_encoder.md)

An encoder can be defined on its own, or can be associated to an axis
to add some extra checks before and after a movement.

## Example of standalone encoder

```
controller:
  class: icepap
  host: iceid42
  encoders:
      - name: m4enc
        address: 25
        steps_per_unit: 1e5
```

## Example of axis encoder

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
  encoders:
      - name: m4enc
        address: 25
        steps_per_unit: 1e5
```


## configuration parameters

* `name`
    * Encoder object's name.
* `steps_per_unit`
    * This value is used to define the conversion factor between
    encoder steps value and real position in user unit. It must be
    accurate to allow comparison between position required by user and
    real position.
* `tolerance`
    * Value in **user_units**.
    * At end of a movement, the encoder value is read and compared to
    the target position of the movement. If the difference is outside
    the limit fixed by the **encoder tolerance** (beware to not
    confuse with Axis tolerance), an exception is raised with message:
    `"didn't reach final position"`




## Usage

see: [encoder usage](motion_encoder.md)


## Icepap encoder

For specific details about icepap encoders, see
[Icepap Encoder Configuration](config_icepap.md#encoder-configuration)


