# Configuring a VSCANNER

Vscanner has 2 axes.

More info here: [http://wikiserv.esrf.fr/bliss/index.php/Vscanner](http://wikiserv.esrf.fr/bliss/index.php/Vscanner)

!!! warning
    For a move of the 2 axes, velocity is the same for both
    axes and the used one is taken from the first one.

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
NO	| NO      | NO

## YAML configuration file example

```yaml
  controller:
    class: VSCANNER
    serial:
        url: ser2net://lidXXX.esrf.fr:29000/dev/ttyRP6
    axes:
      - acceleration: 1
        backlash: 0
        high_limit: 9
        low_limit: 0
        chan_letter: X
        name: vs1
        steps_per_unit: 1
        tolerance: 0.01
        velocity: 1
        tango_server: vscan_samp
    axes:
      - acceleration: 1
        backlash: 0
        high_limit: 9
        low_limit: 0
        chan_letter: Y
        name: vs2
        steps_per_unit: 1
        tolerance: 0.01
        velocity: 1
        tango_server: vscan_samp
```
