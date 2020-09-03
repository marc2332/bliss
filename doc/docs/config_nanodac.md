# Nanodac with **regulation plugin**:

## yml configuration example

Eurotherm Nanodac, acessible via Ethernet


```yml
- class: Nanodac
  plugin: regulation
  module: temperature.eurotherm.nanodac
  controller_ip: 160.103.30.184
  name: nanodac
  inputs:
    - name: nanodac_in1
      channel: 1
      secondary: False # default(False) if True read the secondary input
  outputs:
    - name: nanodac_out1
      channel: 1
  ctrl_loops:
    - name: nanodac_loop1
      channel: 1
      input: $nanodac_in1
      output: $nanodac_out1
```

