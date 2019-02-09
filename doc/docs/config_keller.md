# Keller Pressure Transmitter


## Yaml sample configuration
```YAML
- name: keller_1
  module: keller
  class: PressureTransmitter
  serial:
    url: rfc2217://lid032:28008
  address: 250
  counters:
  - counter_name: k1_p
    type: P1
  - counter_name: k1_t
    type: T1
```

- controller name (mandatory)
- module name (mandatory = 'keller')
- class name (mandatory = 'PressureTransmitter')
- serial line configuration (mandatory)
- serial line url (mandatory)
- serial number (optional). If given, the connected keller must match the expected
- address (optional, default=250 meaning use the transparent address). Most times don't need to give it.
- list of counters
    - counter name (mandatory)
    - counter type (optional, default='P1').  Available types: P1, P2, T1, T2, T. Most kellers only have P1 and T1
