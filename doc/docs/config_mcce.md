# MCCE (Module de Command et Control des Electrometres)
Acessible via serial line, using proprietary ASCII protocol.
Each module can handle up to 2 channels.

The parameters of the serial line are:
8 bits, no parity, 1 stop bit, 9600 bauds

Manifacturer: NOVELEC S.A.

### Example YAML configuration file ###
```yaml
class: Mcce
channels:
  -
    name: mcce1_ch1
    address: 1
    serial:
      url: "rfc2217://ld231:28100"
  -
    name: mcce1_ch2
    address: 2
    serial:
       url: "rfc2217://ld231:28016"
  -
    name: mcce2_ch1
    address: 3
    serial:
       url: "rfc2217://ld231:28017"
  -
    name: mcce2_ch2
    address: 4
    serial:
       url: "rfc2217://ld231:28017"
```

!!! warning
    **address** should be unique, predefined in the hardware integer,
    starting from 1.

**serial** can be either ser2net or Tango url

The plugin for this controller is `bliss`.
```yaml
   plugin: bliss
```
should either be in \_\_init__.yml in the same directory or added to the
above configuration.
