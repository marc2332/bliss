# Micos Motor controller

This Bliss controller has been only tested with a Taurus controller (Firmware version 2.39) model and a Micos UPR160 AIR stage (air-bearing rotation stage).


## Configuration example
```YAML
   controller:
     class: micos
    serial:
      url: ser2net://lid102:28000/dev/ttyR0
    name: micos
    description: EH2 micos motor controller
    axes:
    - name: ths
      number: 1
      steps_per_unit: 1 
      velocity: 60
      acceleration: 100
      low_limit: -10000.0
      high_limit: 10000.0 
      low_endswitch_type: 2
      high_endswitch_type: 2
      hw_low_limit: -10000.0
      hw_high_limit: 10000.0
      tofrom_endsw_velocity: 5
      to_reference_velocity: 10 
      action_at_powerup: 32
      cloop_on: True
      cloop_winsize: 10E-3
      cloop_gstbit5sel: True
      cloop_trigopsel: 0
      cloop_wintime: 1.2E-3
      encoder: $ths_enc
      check_encoder: False
      home_position: -129
    encoders:
    - name: ths_enc
      number: 1
      steps_per_unit: 65550
```

above example works in case there is a \_\_init__.yml in the same directory containing

    plugin: emotion 

The configuration `encoders` entry is optional, but if you want to perform continuous scans using the **FSCAN** framework (https://gitlab.esrf.fr/bliss/fscan) for instance, this is the only way to read the encoder resolution to convert the encoder steps into user unit.


## How to initialize the Micos controller after power off

After switching on the Micos motor controller and the compressed air we must execute this function (via reset_axis()).
This command not only initializes axis with the last saved parameters, but also moves axis to some place and set position to be 0 there.

Therefore after reset_axis() call, we must proceed to home search:

```python
CDI [14]: ths.reset_axis()
CDI [15]: ths.home()
Moving ths from 100.02 to home
CDI [16]: 'ths` dial position reset from 124.639175 to 0.000168
'ths` position reset from 5.639128999999987 to -119.0 (sign: 1, offset: -119.000153)

```


## Further reading at ESRF

*   [Micos id01 wiki](http://wikiserv.esrf.fr/id01/images/2/29/Venus-2_1_9_eng_A4.pdf)
