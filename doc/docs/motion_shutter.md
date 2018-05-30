# Shutter objects

This chapter describes the `bliss.common.shutter.Shutter` class, a generic base class for shutter
implementation. Some motor controllers like **IcePAP** can provide `Shutter` objects. Other
`Shutter` objects include Tango shutters (safety shutter, frontend) for example.

## API

* `open()`: to open the shutter
* `close()`: to close the shutter
* `state()`: returns shutter state
    - one of `OPEN`, `CLOSED` or `UNKNOWN` (constants)
* `state_string()`: return the shutter state as a string
    - `"OPEN"`, `"CLOSED"`, `"UNKNOWN"`
* `.mode` property, to specify or tell in which mode the shutter operates
    - `MANUAL`: the shutter can be opened or closed manually with the `.open()` and `.close()` methods
    - `EXTERNAL`: the shutter is externally controlled - if the external control handler is known to
      the shutter object, it is used when calling `.open()` or `.close()`, otherwise commands will be
      refused;
    - `CONFIGURATION`: the shutter is in configuration (tuning) mode, it cannot be opened or closed
* `.set_external_control(set_open, set_closed, is_opened)`: set the shutter in `EXTERNAL` mode, and
create an external control handler using the 3 callback functions passed in parameter (more details below)
* `.measure_open_close_time()`: put the shutter in `MANUAL` mode, then do open/close sequence to measure
  the time it takes
* `.opening_time`: return known opening time (see `.measure_open_close_time()`)
* `.closing_time`: return known closing time (see `.measure_open_close_time()`)

## External control

External control handler for the shutter can be specified in the configuration, using the
`external-control` key. The corresponding object musst derive from a `bliss.common.shutter.ShutterSwitch`
object.

As a convenience, external control handler for a shutter can also be specified using the `.set_external_control`
method. In this case, 3 callback functions have to be passed:

* function that opens the shutter (e.g. activating **BTRIG** MUSST output)
* function that closes the shutter (e.g. setting **BTRIG** to 0 on MUSST object)
* function that returns `True` if shutter is opened

### External control example from MX beamline

This code is part of the MD2S diffractometer controller. `fshutter` is an IcePAP shutter
configured in BLISS. The shutter is set in `EXTERNAL` mode, it moves when a TTL signal
is received on the IcePAP controller. The TTL signal is triggered by the MD2S itself
when doing the oscillation (continuous scan). It is possible to generate a TTL
pulse by sending commands to the MD2S controller: this is how user can also operate the
shutter on demand. The 3 Python lines below show how to use `set_external_control` to
achieve this configuration:

    fshutter = config.get("fshutter")
    if fshutter:
        fshutter.set_external_control(functools.partial(self._exporter.writeProperty, "FastShutterIsOpen", "true"),
                                      functools.partial(self._exporter.writeProperty, "FastShutterIsOpen", "false"),
                                      lambda: self._exporter.readProperty("FastShutterIsOpen") == "true")




