# Micos Motor controller

## Configuration example from ID10 EH2
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
      tango_server: eh2_micos
      tags: micos
      user_tag:
      - EH2.MICOS
```

above example works in case there is a \_\_init__.yml in the same directory containing

    plugin: emotion 

## further reading at ESRF

*   [Micos id01 wiki](http://wikiserv.esrf.fr/id01/images/2/29/Venus-2_1_9_eng_A4.pdf)
