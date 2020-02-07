# Linkam TMS94 or T95 with **regulation plugin**:
```
Linkam Controllers

Linkam TMS94, acessible via Serial line (RS232)

yml configuration example:

- class: LinkamTms94 # LinkamT95

  module: regulation.temperature.linkam.linkam_TMS94_T95
  plugin: regulation
  name: linkamtms94
  timeout: 3
  serial:
    url: ser2net://lid15a1:28000/dev/ttyRP21
    #baudrate: 19200       # <-- optional

  inputs:
    - name: linkam1_in

  outputs:
    - name: linkam1_out
      low_limit: -196.0     # <-- minimum device value [Celsius]
      high_limit:  600.0    # <-- maximum device value [Celsius]

  ctrl_loops:
    - name: linkam1_loop
      input: $linkam1_in
      output: $linkam1_out
```

