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

The configuration is a matter of defining the following:
- Provide connection informations
- Map PLC input/output plugged modules
- Assign some meaningful *logical names* to input/output
- Define counters
- Define counter gain
- If interlocks are present provide the configuration

### Connection informations ###

The connection can be direct with the following configuration:

```yaml
modbustcp:
    url: host:port
```
Example
```yaml
modbustcp:
    url: wcid31l
```
If you don't specify the port the *default Modbus port 502* is taken which is always the case for real PLC.

Or we can have a connection through a Tango Device Server using the Fully Qualified Domain Name (FQDN).

```yaml
tango:
    url: tango://host:port/domain/family/member
```
Example
```yaml
tango:
    url: tango://lid32ctrl1:20000/ID32/wcid32c/tg
```
Normally host:port can also be omitted if we define the global variable `TANGO_HOST`.

Note: If the connection is through Tango and the property `config` is set we can omit the mapping. 

### Mapping PLC input/output plugged modules ###

Here is given a basic example of yaml configuration:

```yaml
name: wcid31l
plugin: bliss
description: ID31 EH I/O Station
module: wago.wago
class: Wago
modbustcp:
    url: wcid31l
```

Basic information have the purpose to identify the device, the kind of device and the host address to allow communications.

As the PLC can be composed following user needs we have to specify what modules are
attached to the Main CPU, this is done using the `type` keyword. Than we want to
give a name to single input/output and this is done using the `logical_names` keyword.

If the input/output module has, for example, 4 inputs, we can't give more than 4 logical_names,
but we can use the same name twice or more to logically group them. In this case we can still
distinguish them later accessing to the `logical_channel`.

Let's take this example:

```yaml
name: wcid31l
plugin: bliss
description: ID31 EH I/O Station
module: wago.wago
class: Wago
modbustcp:
    url:wcid31l 
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
  - type: 750-436
    logical_names: o1, o2, o3, o4, o5
ignore_missing: True
counter_names: pot1vol, pot1cur, pot2vol, pot2cur, i0
counter_gain_names: i0_g
```

We can see that `i0_g` is used three times and so we are mapping three input/output with the
same `logical_name` and they will have a `logical_channel` with a progressive number starting
from zero. So the first `i0_g` will have logical_channel 0, the second will have 1 and so on.

First, you have to declare the type of board and then you can map the logical names that will be used to access those channels.

Some other examples:

- Card type 750-476 is a 2 Channel +-10V Input, so you will declare 2 logical names from which you will expect float values.
- Card type 750-530 is an 8 Channel Digital Output, so you will declare 8 logical names and you will expect and use boolean data.
- The last Card type shows how to behave in the case that there is nothing attached to the channel: you can just map with an underscore.

The key `counter_names` have to be organized as a comma separated list of logical names. These names should be already defined in the preceding mapping.
The key `counter_gain_names` associates a counter with gains when the hardware requires it (e.g.novelec electrometer with 3 different gains).

### Ignore not mapped channels ###

The additional key `ignore_missing` is used to avoid exception if a channel is not mapped on `logical_names`. Be aware that we can avoid defining
last channels on the module, but we can't skip.

For example we can go from this:

```yaml
mapping:
  - type: 750-530
    logical_names: p9,p10,p11,p12,p13,pso,wcdm2c7,wcdm2c8
```
To this:
```
ignore_missing: True
mapping:
  - type: 750-530
    logical_names: p9,p10,p11,p12
```
Using `_` underscore to map unused channels is a convention but is not ignoring them, simply mapping with the name `_`.

# Interlock Protocol #

## What is Interlock Protocol? ##

Interlocks Protocol developed at ESRF is a way to use Wago PLC to continously monitor for some input conditions and
trigger a relay output when those conditions meet a thresholds.

### What is the purpose? ###

Let's imagine that some hardware of a beamline has to maintain a temperature beetween 20 and 80 degrees.
Going under 20 degrees or over 80 may cause a hardware damage and imagine that in that case we would like to shutdown the power supply.

This is the tipical case of use of interlocks protocol.

### More details ###

On the same PLC we can have one or more `interlock instances` running where one interlock instance is made by:

 - One PLC's digital output normally associated with a relay
 - One or more control conditions (input/output channels of the PLC)

Each control signal of an interlock instance has a defined "alarm condition". 
This condition is a defined logic value (ON or OFF) for digital signals and
a value range (defined by MIN/MAX thresholds) for analog signals.
Whenever one of the control signal reaches an alarm condition, the interlock
instance goes into "tripped" state and the alarm relay switches to the alarm
position. 
By default the alarm position is OFF (relay open) but this can be inverted
in the configuration of the interlock instance.

One can configure more than one interlock instance in a Wago controller.
The controller stores the configuration in its internal non-volatile memory
and is completely autonomous: as long it is switched on, the configured
interlock functions are active.

The configuration is at first created in Beacon and then through Bliss
we can display, upload and check the configuration of the interlock instances in
the controller itself.


## Steps to to make it works ##

To have this kind of interlocks system working we need these steps:

 1. An interlock program `isgmain` should be loaded on the PLC normally by ESRF Electronic group, this program is generic (always the same
    for all PLCs)
 2. Conditions have to be defined in the Beacon YAML configuration for that PLC
 3. Conditions have to be uploaded to the PLC using the Bliss shell command `interlocks_upload`
 4. From here on the PLC will operate by himself checking inputs and eventually
    activating relays; no need for Bliss to be active.

### YAML configuration for interlocks ###

Insert the `interlocks` keyword in the same Wago configuration file seen above.
Than specify a list of interlocks.

```yaml
interlocks:
    - relay: intlckf
      flags: STICKY
      name: Interlock 1
      channels:
          - logical_name: esTf1
            type: TC
            min: 10
            max: 50
          - logical_name: esTf2
            logical_channel: 1
            type: TC
            min: -10
            max: 50.5
    - relay: intlckf
      relay_channel: 2
      flags: STICKY
      name: Interlock 2
      channels:
          - logical_name: esTr1
            type: TC
            min: -10
            max: 50.5
          - logical_name: o2
            type: OB
``` 

### Configuration of the relay ###

- relay: (**Mandatory**) is the `logical name` that will be activated in case of triggering
- relay_channel: (**default is 0**) is the `logical channel` that will be triggered, this is because we can assign the same name to more than one input/output and consequently the will have different channel: the first will be 0, the second 1 and so on.
- flags: (**Optional**)
    - `STICKY`: once conditions are meet and the relay is activated, we should manually
                send the command `interlock_reset` through Bliss to reset it.
    - `INVERTED`: the behaviour of the relay is Inverted: normally the relay is closed
                 (letting current to pass) during operations and if triggered it will
                 open (avoiding current to pass). If we put this flag the behaviour will
                 be inverted.
    - `NOFORCE`: by default when there is no alarm condition, the alarm relay is forced to
                 the normal position and cannot be switched externally. The NOFORCE flag
                 relaxes this constraint. In any case when the instance trips, the relay is
                 always forced into the alarm state.
- name: (**Optional**) is simply an user description of the purpose of the interlock condition.

### Configuration of the channel ###

We can have digital or analog channels, the following are common config:

- logical_name: (**Mandatory**) is the `logical_name` of the input/output that will be check, this
                has to be defined in the `mapping`.
- type: (**Mandatory**)
    - IB: Input Binary type (digital input)
    - OB: Output Binary type (digital output)
    - IW: Input Word value
    - OW: Output Word value
    - IV: Input Voltage
    - OV: Output Voltage
    - TC: Termocouple
- flags: (**Optional**)
    - INVERTED: The logic of alarm condition can be inverted with the INVERTED flag. By
                default digital control channels are normally ON and switch into alarm
                condition when they become OFF, and analog channels trip when their value
                is out of the min/max thresholds as explained above.
    - STICKY: The STICKY flag has the same function than when it is used as an instance
              flag, but in this case it is associated to a particular channel and only
              takes effect when this channel is the one that trips.


In the case of an analog input/output signal we will have also

- min: lower limit, going under will trigger the relay
- max: higher limit, going over will trigger the relay

For termocouple the precision can be given in decimal, E.G. 50.7 Celsius.


## Interlocks on Bliss shell ##

`interlock_show()` can be used to obtain interlocks info concerning all Wagos already imported from yaml file or with `config.get`.

```python
BLISS [16]: wcid21hpps = config.get("wcid21hpps")
BLISS [17]: interlock_show()
Currently configured Wagos: wcid21hpps


Interlocks on wcid21hpps
Interlock configuration is not present in Beacon
On PLC:
1 interlock instance
  Instance #1   Description:
    Alarm relay = intlckhpps[0]  STICKY                             [ON]
    State = NOT TRIPPED
    10 channels configured:
      # 1  .... - hppstc1  TC  Low:0.0000 High:50.0000  STICKY      [23.5]
      # 2  .... - hppstc2  TC  Low:0.0000 High:50.0000  STICKY      [23.1]
      # 3  .... - hppstc3  TC  Low:0.0000 High:50.0000  STICKY      [23.2]
      # 4  .... - hppstc4  TC  Low:0.0000 High:50.0000  STICKY      [23.0]
      # 5  .... - hppstc5  TC  Low:0.0000 High:50.0000  STICKY      [23.1]
      # 6  .... - hppstc6  TC  Low:0.0000 High:50.0000  STICKY      [23.3]
      # 7  .... - hppstc7  TC  Low:0.0000 High:50.0000  STICKY      [23.3]
      # 8  .... - hppstc8  TC  Low:0.0000 High:50.0000  STICKY      [23.6]
      # 9  .... - pptc1  TC  Low:0.0000 High:50.0000  STICKY        [14.1]
      #10  .... - pptc2  TC  Low:0.0000 High:50.0000  STICKY        [14.4]
```

The same command can be used as a method of a single Wago.

```python
BLISS [14]: wago_simulator = config.get("wago_simulator")
BLISS [15]: wago_simulator.interlock_show()
Interlocks on wago_simulator
Interlock Firmware is not present in the PLC

On Beacon:
2 interlock instance
  Instance #1   Description: Interlock
    Alarm relay = intlckf1[0]  STICKY                               [None]
    State = NOT TRIPPED
    4 channels configured:
      # 1  .... - esTf1  TC  Low:10.0000 High:50.0000               [None]
      # 2  .... - esTf2  TC  Low:-10.0000 High:50.5000              [None]
      # 3  .... - esTr1  TC  Low:10.0000 High:50.0000               [None]
      # 4  .... - esTr2  TC  Low:10.0000 High:50.0000               [None]

  Instance #2   Description: _Interlock 2
    Alarm relay = intlckf2[0]  STICKY                               [None]
    State = NOT TRIPPED
    2 channels configured:
      # 1  .... - esTr1  TC  Low:-10.0000 High:50.5000              [None]
      # 2  .... - esTr2  TC  Low:-10.0000 High:50.0000              [None]
```

The interlock show will check both Beacon configuration and Hardware configuration and will make evidence of any difference.



