# HMC8041 configuration

Controller for Rhode&Schwartz HMC8041 Power Supply.

The controller class provides basic access to:

- voltage (Volt) measured value, setpoint and limit range
- current (Amp) measured value, setpoint and limit range
- power (W) measured
- ramp status (on/off) and ramp duration (sec)

Optionnaly, counters can be configured for measured value of:

- voltage
- current
- power

## Configuration example (yml)

```yml
- class: HMC8041
  module: powersupply.hmc8041
  name: hmc
  tcp:
    url: phosphor2.esrf.fr:5025
  counters:
    - name : hmc_volt
      tag: voltage
    - name: hmc_curr
      tag: current
```

