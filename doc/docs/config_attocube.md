## Configuring a AMC100 piezo motor


This chapter explains how to configure a piezo motor from
Attocube.

### YAML config file example
```yaml
 - class: AMC100
      host: lid15amc100
      axes:
        - name: pz
          channel: 0
          type: ECSx5050        # positioner type
          close-loop: false      # default
          target-range: 100     # is basically the window size for the closed loop (100nm)
          autopower: true       # default
          steps_per_unit: 1000. # μm
          amplitude: 25000      # 25 Volts
          velocity: 1000     # here is the movement frequency (here 1kHz)
```

!!!note
Only tested in open loop (for now)