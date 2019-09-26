# Wago Programmable Logic Controllers #

## Communication with Wago PLCs ##

The communication is implemented throught the standard Modbus/TCP protocol.

## Modbus Protocol ##

The standard Modbus serial protocol defines mainly:

* 4 memory areas on the device that can be accessed writing, reading or both
* how to construct and send requests to the device and how to interpret responses

What the protocol does not define are information contained in those specific memory areas as this is device dependent.
In order to obtain this information is necessary to consult the documentation provided by the producer.

The Modbus/TCP protocol is built on top of the Modbus serial protocol as it encapsulates Modbus messages through a TCP/IP socket usually on standard port 502.

## Wago PLCs ##

Wago PLCs are usually composed by a main core board plus some number of additional boards as needed containing Input or Output channels.
The bliss wago class access these values reading or writing specific modbus registers.
The user is allowed to map these input/output channels with string names through the yml file as described after.

## Configuration ##

The configuration should explain in particular which kind of input/output boards are attached to the core board in order to interrogate the device properly

### Basic example YAML configuration file ###

```yaml
name: wcid31l
description: ID31 EH I/O Station
class: wago
controller_ip: 160.103.51.20
```

Basic information have the purpose to identify the device, the kind of device and the net address to allow communications.

### More complete example of YAML configuration file ###

```yaml
name: wcid31l
description: ID31 EH I/O Station
class: wago
controller_ip: 160.103.51.20
mapping:
  - type: 750-476
    logical_names: pot1vol, pot1cur
  - type: 750-530
    logical_names: p9,p10,p11,p12,p13,pso,wcdm2c7,wcdm2c8
  - type: 750-478
    logical_names: pot1out, adc8
  - type: 750-478
    logical_names: pot2out, adc10
  - type: 750-562
    logical_names: dac5, dac6
  - type: 750-562-UP
    logical_names: pot1in, dac8
  - type: 750-469
    logical_names: th_mask, _
  - type: 750-516
    logical_names: i0_g,i0_g,i0_g,_
  - type: 750-467
    logical_names: i0,_
counter_names: pot1vol, pot1cur, pot2vol, pot2cur, i0
counter_gain_names: i0_g
```

The mapping describes all additional cards attached to the core main board providing Input/Output features.

First, you have to declare the type of board and then you can map the logical names that will be used to access those channels.

* Card type 750-476 is a 2 Channel +-10V Input, so you will declare 2 logical names from which you will expect float values.
* Card type 750-530 is an 8 Channel Digital Output, so you will declare 8 logical names and you will expect and use boolean data.
* The last Card type shows how to behave in the case that there is nothing attached to the channel: you can just map with an underscore.

The key `counter_names` have to be organized as a comma separated list of logical names. These names should be already defined in the preceding mapping.
The key `counter_gain_names` associates a counter with gains when the hardware requires it (e.g.novelec electrometer with 3 different gains).
