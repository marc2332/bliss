# Oxford 800 used with **Regulation plugin**:

## YAML configuration file example

```YAML
  - class: oxford800
    plugin: regulation
    module: temperature.oxford.oxford800
    cryoname: id10oxford800

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

Use the oxford800 hostname as the **cryoname** in the YML configuration file.

!!! note
    Contrary to the Oxford700, the 800 model communication library is not part of Bliss.
    
    You have to install the liboxford800 first.
    
To Install the library, clone the gitlab project and pip install:

```bash
$ git clone https://gitlab.esrf.fr/bliss/liboxford800
$ . blissenv
$ cd liboxford800
$ (bliss_dev) pip install -e .
```

This model has a network connection in 10 Mbits Half Duplex.  It work
nicely in DHCP, you can find the MAC address on the device screen in
the network menu.  As soon as the controller is connected to the
network, it starts to send udp packet.

To check lib install and connectivity:

```bash
python -c "from bliss.controllers.regulation.temperature.oxford import oxford800;oxford800.ls_oxford800()"
```


## Usage

In the Bliss session import the Loop object (ex: `ox_loop`).

Access the controller with `ox_loop.controller`.

Access the associated input and output with `ox_loop.input` and `ox_loop.output`.

Perform a scan with the regulation loop as an axis with `ox_loop.axis`.

Ramp to a given setpoint temperature with `ox_loop.setpoint = 200`.

Change the ramp rate with `ox_loop.ramprate = 360`  (in [0, 360]).

If ramprate is set to zero (`ox_loop.ramprate = 0`), the controller will reach
to the setpoint temperature as fast as possible.

## Status Information

In a Bliss session, type the name of the loop to show information about the
Loop, its controller and associated input and output.

## further reading
   * [Oxford 700 and 800 series: communication protocol](https://connect.oxcryo.com/serialcomms/700series/cs_status.html)


