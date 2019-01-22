# Configuring a VSCANNER

Vscanner has 2 axes.

More info here: [http://wikiserv.esrf.fr/bliss/index.php/Vscanner](http://wikiserv.esrf.fr/bliss/index.php/Vscanner)

## YAML configuration file example


```
-
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