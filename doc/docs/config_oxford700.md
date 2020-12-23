# Oxford 700 used with **Regulation plugin**:

## YAML configuration file example

```YAML
  - class: oxford700
    plugin: regulation
    module: temperature.oxford.oxford700
    serial:
      url: rfc2217://lid032:28008
      
    inputs:
      - name: ox_in
    outputs:
      - name: ox_out
    ctrl_loops:
      - name: ox_loop
        input: $ox_in
        output: $ox_out
        ramprate: 350   # (optional) default/starting ramprate [K/hour]
```

## Usage

In the Bliss session import the Loop object (ex: `ox_loop`).

Access the controller with `ox_loop.controller`.

Access the associated input and output with `ox_loop.input` and `ox_loop.output`.

Perform a scan with the regulation loop as an axis with `ox_loop.axis`.

Ramp to a given setpoint temperature with `ox_loop.setpoint = 200`.

Change the ramp rate with `ox_loop.ramprate = 360`  (in [0, 360]).

If ramprate is set to zero (`ox_loop.ramprate = 0`), the controller will reach to the setpoint temperature as fast as possible.


## Status Information

In a Bliss session, type the name of the loop to show information about the Loop, its controller and associated input and output.

## further reading
   * [Oxford 700 and 800 series: communication protocol](https://connect.oxcryo.com/serialcomms/700series/cs_status.html)

## further reading at ESRF
   * [Sample env. Wiki: Oxford Cryosystems - Cryostream Controller 700](http://wikiserv.esrf.fr/sample_env/index.php/Oxford_Cryosystems_-_Cryostream_Controller_700)
   * [Bliss Wiki: Oxford700](http://wikiserv.esrf.fr/bliss/index.php/Oxford700)
   