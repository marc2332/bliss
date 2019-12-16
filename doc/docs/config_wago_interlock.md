
# Interlock Protocol #

## What is Interlock Protocol? ##

Interlocks Protocol developed at ESRF is a way to use Wago PLC to continuously monitor for some input conditions and
trigger a relay output when those conditions meet a thresholds.

### What is the purpose? ###

Let's imagine that some hardware of a beamline has to maintain a temperature between 20 and 80 degrees.
Going under 20 degrees or over 80 may cause a hardware damage and imagine that in that case we would like to shutdown the power supply.

This is the typical case of use of interlocks protocol.

### More details ###

On the same PLC we can have one or more `interlock instances` running where one interlock instance is made by:

* One PLC's digital output normally associated with a relay
* One or more control conditions (input/output channels of the PLC)

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


`interlock_show()` will display interlocks info concerning all Wagos
already imported from yaml file or with `config.get`. 
During the execution of this command the configuration loaded into Wagos
will be downloaded and compared with the existing in Beacon. If
differences are found they will be printed in the shell.

`interlock_show(*wagos)` will display interlocks info only for given Wagos.

`interlock_state()` returns a tuple containing the actual state
of the interlocks, useful also in scripts or status bar for monitoring.
If you use it inside a script you have to import it with 
`from bliss.common.standard import interlock_state`
Without arguments it will return

`interlock_state(*wagos)` will return states only for given Wagos.

## Methods attached to Wago objects ##

`wago_instance.interlock_reset(instance_num)` it will reset a specific
relay instance.

`wago_instance.interlock_upload()` will upload the configuration for the
given `wago_instance` from beacon to the plc.

`wago_instance.interlock_to_yml()` will download the actual configuration from
the wago and give back as an YML string. Very useful on an existing plc
that you wish to convert from spec to Bliss.

`wago_instance.interlock_state()` will print the state of interlock relays for
the given `wago_instance`.

### interlock_show ##

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

The same command can be used as a method of a the Wago.

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
