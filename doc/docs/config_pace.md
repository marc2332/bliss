# PACE 6000 used with **Regulation plugin**:

## YAML configuration file example

```YAML
- class: Pace
  plugin: regulation
  name: pace_ctrl
  tcp:
      url: id15pace6000:5025
  inputs:
    - name: pace1_in
      channel: 1
    - name: pace2_in
      channel: 2
  outputs:
    - name: pace1_out
      channel: 1
    - name: pace2_out
      channel: 2
  ctrl_loops:
    - name: pace1
      input: $pace1_in
      output: $pace1_out
    - name: pace2
      input: $pace2_in
      output: $pace2_out
```

Opionnaly, `unit` can be specified for each input/output channel. If not specfified, `unit` is read from the controller, otherwise it is set on the controller. Supported units by the controller are : "ATM", "BAR", "MBAR", "PA", "HPA", "KPA", "MPA", "TORR", "KG/M2"

## Usage

In the Bliss session import the Loop object (ex: `pace1`).

Access the controller with `pace1.controller`.

Access the associated input and output with `pace1.input` and `pace1.output`.

Perform a scan with the regulation loop as an axis with `pace1.axis`.

Ramp to a given setpoint temperature with `pace1.setpoint = 200`.

Change the ramp rate with `pace1.ramprate = 10`.

If ramprate is set to zero (`pace1.ramprate = 0`), the controller will reach to the setpoint temperature as fast as possible.


## Status Information

In a Bliss session, type the name of the loop to show information about the Loop, its controller and associated input and output.

## further reading
   * [PACE presentation] (https://www.bakerhughesds.com/druck/pressure-controllers-indicators)
   * [PACE manual] (https://www.bakerhughesds.com/sites/g/files/cozyhq596/files/2019-08/eng_-_pace_1000_5000_6000_calibration_manual_k0450_rev_b.pdf
   * [PACE scpi commands] (https://www.bakerhughesds.com/sites/g/files/cozyhq596/files/2020-06/k0472.pdf)

