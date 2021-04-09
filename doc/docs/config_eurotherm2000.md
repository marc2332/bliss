# Eurotherm 2000 series used with **Regulation plugin**:

## YAML configuration file example

```YAML
class: Eurotherm2000
plugin: regulation
module: temperature.eurotherm.eurotherm2000
serial:
    url: /dev/ttyS0
inputs:
    - name: euro_in
      unit: '°C'
outputs:
    - name: euro_out
      unit: '%'
ctrl_loops:
    - name: euro_loop
      input: $euro_in
      output: $euro_out
```

Opionnaly, `unit` can be specified for each input/output channel.

## Usage

In the Bliss session import the Loop object (ex: `euro_loop`).

Type the name in the bliss shell to print informations.

```python

TEST_BCU [5]: euro_loop
     Out [5]:
            === Loop: euro_loop ===
            controller: Eurotherm2480 (READY)
            Input: euro_in @ 22.619 °C
            output: euro_out @ 4.398 %

            === Setpoint ===
            setpoint: 23 °C       
            ramprate: 10 °C/min   
            ramping: False        

            === PID ===           
            kp: 400               
            ki: 180               
            kd: 1
```

Access the associated input and output with `euro_loop.input` and `euro_loop.output`.

Ramp to a given setpoint temperature with `euro_loop.setpoint = 23`.

Change the ramp rate with `euro_loop.ramprate = 10`.

If ramprate is set to zero (`euro_loop.ramprate = 0`), the controller will reach the setpoint temperature as fast as possible.

Get current input temperature with `euro_loop.input.read()`.

Perform a scan with the regulation loop as an axis with `euro_loop.axis`.

Access the controller with `euro_loop.controller` and all expert commands with `euro_loop.controller.cmds`.

All current values of the controller parameters can be retrived with `euro_loop.controller.dump_all_cmds`.


## Status Information

In a Bliss session, type the name of the loop to show information about the Loop, its controller and associated input and output.

Use `euro_loop.controller.status` or `euro_loop.controller.state` to retrieve information about the controller.

