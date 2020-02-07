# Meerstetter used with **temperature plugin**:

## Configuration example
```YAML
    - class: ltr1200
    module: meerstetter.ltr1200
    host: 160.103.23.56
    dev_addr: 1
    outputs:
        - name: heater
```

aboves example works in case there is a \_\_init__.yml in the same directory containing

    plugin: temperature

In case there is no \_\_init__.yml this line needs to be added the device configuration

## further reading at ESRF

*   [LTR-1200 bliss wiki](http://wikiserv.esrf.fr/bliss/index.php/LTR-1200)
*   [LTR-1200-TEC1123 sample env wiki](http://wikiserv.esrf.fr/sample_env/index.php/LTR-1200-TEC1123)
