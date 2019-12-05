# Wago Programmable Logic Controllers #

## Communication with Wago PLCs ##

The communication is implemented through the standard Modbus/TCP protocol.

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

We can connect to Wago in two ways:

- direct connection
- through Tango Device Server



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

### Simulation ###

We can simulate any Wago simply installing requirements-dev-conda and
adding the following entry to the configuration:
```yaml
simulate: True
```
This will launch a simulator on localhost (and a random port) ignoring other
connection settings.
You can use this simulator for basic testing, be aware that is initialized
with random values and than it will keep the last value set.
Also don't forget the flag `simulate: True` if you want to connect to the
real Hardware!

## Basic usage from the shell ##

Normally you would simply need `set` and `get` methods

```python
BLISS [1]: w = config.get("transfocator_simulator")
BLISS [2]:
BLISS [2]:
BLISS [2]: wago_simulator = config.get("wago_simulator")
BLISS [3]: wago_simulator
  Out [3]:  logical device     num of channel   module_type              description
           ----------------  ----------------  -------------  ----------------------------------
               foh2ctrl                     4     750-504          4 Channel Digital Output
               foh2pos                      4     750-408          4 Channel Digital Input
                sain2                       1     750-408          4 Channel Digital Input
                sain4                       1     750-408          4 Channel Digital Input
                sain6                       1     750-408          4 Channel Digital Input
                sain8                       1     750-408          4 Channel Digital Input
                 pres                       1     750-408          4 Channel Digital Input
                esTf1                       1     750-469     2 Channel Ktype Thermocouple Input
                esTf2                       1     750-469     2 Channel Ktype Thermocouple Input
                esTf3                       1     750-469     2 Channel Ktype Thermocouple Input
                esTf4                       1     750-469     2 Channel Ktype Thermocouple Input
                esTr1                       1     750-469     2 Channel Ktype Thermocouple Input
                esTr2                       1     750-469     2 Channel Ktype Thermocouple Input
                esTr3                       1     750-469     2 Channel Ktype Thermocouple Input
                esTr4                       1     750-469     2 Channel Ktype Thermocouple Input
               intlckf1                     1     750-517         2 Changeover Relay Output
               intlckf2                     1     750-517         2 Changeover Relay Output
                o10v1                       1     750-554          2 Channel 4/20mA Output
                o10v2                       1     750-554          2 Channel 4/20mA Output

           Given mapping does match Wago attached modules

BLISS [4]: wago_simulator.get("foh2ctrl")
  Out [4]: [1, 0, 1, 1]

BLISS [5]: wago_simulator.set("foh2ctrl",0,0,0,0)
BLISS [6]: wago_simulator.get("foh2ctrl")
  Out [6]: [0, 0, 0, 0]

BLISS [7]: wago_simulator.get("esTr1", "esTr2","o10v1")
  Out [7]: [78.8, -203.4, 44404]

BLISS [8]: wago_simulator.set("esTr1", 0)
!!! === RuntimeError: Cannot write: 'esTr1' is not an output === !!! ( for more details type cmd 'last_error' )

```
