# Smaract motor controller


## Yaml sample configuration

```YAML
- class: SmarAct
  tcp:
     url: smaractid013
  axes:
  - name: a3
    channel: 2
    steps_per_unit: 1000
    sensor_type: S
    hold_time: 60
    velocity: 2000
    acceleration: 0
    tolerance: 1e-1
    user_tag: EH3.SMARACT
  - name: b1
    channel: 3
    steps_per_unit: 1000
    sensor_type: S
    hold_time: 60
    velocity: 2000
    acceleration: 0
    tolerance: 1e-1
    user_tag: EH3.SMARACT

```

## Further reading at ESRF
[bliss wiki: Smaract](http://wikiserv.esrf.fr/bliss/index.php/Smaract)
