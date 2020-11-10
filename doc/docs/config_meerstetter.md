# Meerstetter used with **temperature plugin**:

## Configuration example
```YAML
- class: ltr1200
  plugin: temperature
  module: meerstetter.ltr1200
  host: 160.103.23.56
  dev_addr: 1
  outputs:
    - name: heater
```

## further reading at ESRF

*   [LTR-1200 bliss wiki](http://wikiserv.esrf.fr/bliss/index.php/LTR-1200)
*   [LTR-1200-TEC1123 sample env wiki](http://wikiserv.esrf.fr/sample_env/index.php/LTR-1200-TEC1123)
