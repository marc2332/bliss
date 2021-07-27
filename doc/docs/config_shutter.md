
# Shutter

This chapter describes the `bliss.common.shutter.Shutter` class, a generic base
class for shutter implementation.

Main kinds of shutters in BLISS are:

* [**IcePAP** shutter](config_shutter.md#icepap-shutter) for stepper motor controlled shutters
* [TangoShutter](config_shutter.md#tangoshutter) to manage:
    - Safety shutters
    - Beamline Frontend
    - Vacuum remote-valves

## Shutter API

Here are the common methods usable with shutters.

### Basic functions

* `open()`: to open the shutter (blocking)
* `close()`: to close the shutter (blocking)
* `state()`: return shutter state as a constant
    - one of `OPEN`, `CLOSED` or `UNKNOWN`
* `state_string()`: return the shutter state as a string
    - `"OPEN"`, `"CLOSED"` or `"UNKNOWN"`

### Advanced functions

* `.mode` property, to specify or tell in which mode the shutter operates
    - `MANUAL`: the shutter can be opened or closed manually with the `.open()`
      and `.close()` methods
    - `EXTERNAL`: the shutter is externally controlled - if the external control
      handler is known to the shutter object, it is used when calling `.open()`
      or `.close()`, otherwise commands will be refused;
    - `CONFIGURATION`: the shutter is in configuration (tuning) mode, it cannot
      be opened or closed

* `.set_external_control(set_open, set_closed, is_opened)`: set the shutter in
  `EXTERNAL` mode, and create an external control handler using the 3 callback
  functions passed in parameter (more details below)
* `.measure_open_close_time()`: put the shutter in `MANUAL` mode, then do
  open/close sequence to measure the time it takes
* `.opening_time`: return known opening time (see `.measure_open_close_time()`)
* `.closing_time`: return known closing time (see `.measure_open_close_time()`)


### External control

External control handler for the shutter can be specified in the configuration,
using the `external-control` key. The corresponding object musst derive from a
`bliss.common.shutter.ShutterSwitch` object.

As a convenience, external control handler for a shutter can also be specified
using the `.set_external_control` method. In this case, 3 callback functions
have to be passed:

* function that opens the shutter (e.g. activating **BTRIG** MUSST output)
* function that closes the shutter (e.g. setting **BTRIG** to 0 on MUSST object)
* function that returns `True` if shutter is opened

#### External control example from MX beamline

This code is part of the MD2S diffractometer controller. `fshutter` is an IcePAP
shutter configured in BLISS. The shutter is set in `EXTERNAL` mode, it moves
when a TTL signal is received on the IcePAP controller. The TTL signal is
triggered by the MD2S itself when doing the oscillation (continuous scan). It is
possible to generate a TTL pulse by sending commands to the MD2S controller:
this is how user can also operate the shutter on demand. The 3 Python lines
below show how to use `set_external_control` to achieve this configuration:

```python
fshutter = config.get("fshutter")

fshutter.set_external_control(functools.partial(self._exporter.writeProperty, "FastShutterIsOpen", "true"),
                              functools.partial(self._exporter.writeProperty, "FastShutterIsOpen", "false"),
                              lambda: self._exporter.readProperty("FastShutterIsOpen") == "true")
```




## IcePap shutter

An IcePAP controller can be used in *shutter control mode* (using IcePAP LIST
MODE), to operate the opening and closing of a shutter. This is done by moving
back and forth a stepper motor between two pre-defined positions. The change is
trigger by an external signal.

### Specific IcePAP shutter configuration

* **axis_name**: name of existing IcePAP axis to move as a shutter
* **closed_position**: position of the shutter when it is closed (in user position)
* **opened_position**: position of the shutter when it is open (in user position)

```python
DEMO [1]: fsh
 Out [1]: Shutter (fsh)
          ----------------  ------
          State:            CLOSED
          Mode:             MANUAL
          open position:    20
          closed position:  10
          ----------------  ------
```


In order to change the open/close positions,the icepap shutter must be put in
`CONFIGURATION` mode:
```python
DEMO [15]: fsh.mode = fsh.CONFIGURATION
DEMO [16]: fsh
 Out [16]: Shutter (fsh)
           ----------------  -------------
           State:            UNKNOWN
           Mode:             CONFIGURATION
           open position:    20
           closed position:  10
           ----------------  -------------
```

Then the open/closed positions can be changed:
```python

DEMO [20]: fsh.opened_position = 22

DEMO [21]: fsh.closed_position = 12

DEMO [22]: fsh
 Out [22]: Shutter (fsh)
           ----------------  -------------
           State:            UNKNOWN
           Mode:             CONFIGURATION
           open position:    22
           closed position:  12
           ----------------  -------------
```

And the shutter must be exited from CONFIGURATION mode to be usable:
```python
DEMO [23]: fsh.mode = fsh.MANUAL
```


### IcePap Shutter config

```YAML
controller:
   class: icepap
   host: iceid421
   axes:
       - name: fshut_mot
         address: 22
         ...
   shutters:
       - name: fshutter
         axis_name: fshut_mot             # no $ ???
         external_control: $wago_switch   # external control reference (not mandatory)
         closed_position: 0
         opened_position: 1
```

## TangoShutter

`TangoShutter` class is used to interface Tango Device Servers controlling:

* frontend
* safety shutter
* vaccum remote valves

`open()` and `close()` methods are blocking: the `TangoShutter` object waits the
end of the action before returning.

A timeout (60s by default) triggers a `RuntimeError` in case of failure during
the opening or the closing the shutter.

Some commands/attributes (like `automatic`/`manual`) are only implemented in the
front end device server, set by the `_frontend` variable.


### Usage examples

Example with a safety shutter:
```python
DEMO [1]: bsh1
 Out [1]: Pneumatic Beam Shutter is closed
           - PSS search broken in downstream hutch
           - Experiment interlock
           - RV4 not Open
           - RV6 not Open
```


Example with a vacuum remote valve:
```python
DEMO [6]: rv9.close()
rv9 was OPEN and is now CLOSED

DEMO [8]: rv9
 Out [8]: Pneumatic is closed

DEMO [10]: rv9.open()
rv9 was CLOSED and is now OPEN

DEMO [11]: rv9
 Out [11]: Pneumatic is open

DEMO [12]: rv9.open()
WARNING 2020-03-19 00:13:23,937 global.controllers.rv9: rv9 already open, command ignored
```


### Configuration

parameters:

* `shutter_type` (str, optional) : type of the shutter in : `FrontEnd`; `SafetyShutter`; `Valve`; `Generic`.
  If not specified, TangoShutter will try to automatically find the type.
* `uri` (str): address of the Tango device

Safety shutter and FrontEnd:
```yaml
- name: safshut
  class: TangoShutter
  shutter_type: SafetyShutter
  uri: id42/bsh/1

- name: frontend
  class: TangoShutter
  shutter_type: FrontEnd                # shutter_type is optionnal
  uri: acs.esrf.fr:10000/fe/master/id42

```

Remote valves:
```yaml
- name: rv0
  class: TangoShutter
  shutter_type: Valve
  uri: id42/v-rv/0

- name: rv1
  class: TangoShutter
  shutter_type: Valve
  uri: id42/v-rv/1

- name: rv2
  class: TangoShutter
  shutter_type: Valve
  uri: id42/v-rv/2
```


### FrontEnd mode

If a `TangoShutter` is a FrontEnd, a special attribute `mode` is usable to
activate or deactivate the automatic openning mode.

It can be : `MANUAL` `AUTOMATIC` or `UNKNOWN`

Example:
```python
DEMO [3]: fe
 Out [3]: State     : Fault on Front End
          Mode      : No mode is validated!
          Automatic : Automatic opening off
          Type      : UHV

          Module 1 Gate Valve 1: Open
          Module 2 Gate Valve 1: Close

          Fault, pending interlocks are:
           Beam permission loop was opened!
           Cooling fault on module1 fixed absorber
           Interlock from personal safety system
```

To change the opening mode of a `FrontEnd` shutter:
```python
DEMO [3]: fe.mode = "MANUAL"
fe mode was AUTOMATIC and is now MANUAL
```

Example (during a shutdown):
```python
DEMO [7]: fe.mode = "AUTOMATIC"
!!! === RuntimeError: Cannot set AUTOMATIC opening === !!!
```
