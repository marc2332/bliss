# Keithley configuration

!!! warning
    Changing the `range` changes the *analog out range* ->
    take care to not run a scan in autorange.

!!! note
    Changing the `rate` aka `nplc` does not affect the analog out.

## Configuration

Model 6485 can be configured to terminate each message that it
transmits with any of the following combinations of <CR> and <LF>:

* `LF` line feed `\n`
* `CR` carriage return `\r`
* `LFCR` line feed, carriage return `\n\r`
* `CRLF` carriage return, line feed `\r\n`

When using K6485 via a serial line we have decided for the device server and
BLISS to hard code the configuration with the following parameters:

* Baud rate: `38400`
* Bits: `8`
* Parity: `none`
* Termination character: `LF` (ie `\n`)

So the Keithley controller has to be configured according to that.

To check and change the hardware configuration of the Keithley, follow the sequence:

* press the `config local` button,
* press the `COMM` button. You should see `RS232` or `GPIB`. ( OR
  SHIFT + ZCHK/RS-232 button for the 6514 model )
* with the help of the `Δ` / `∇` buttons (right most on the front
  panel) you could go through all the parameters and change them if
  needed.
* to end the procedure press `ENTER` and then `EXIT`.

The instrument keeps the setup when switched off.

### Minimum

```yaml
plugin: keithley
keithleys:
  - model: 2000
    gpib:
      url: enet://gpibid11c.esrf.fr
      pad: 22
    sensors:
      - name: pico6
        meas_func: VOLT
        address: 1

  - model: 6485
    gpib:
      url: enet://gpibid11c.esrf.fr
      pad: 23
    sensors:
      - name: pico7
        address: 1
```

### Full

```yaml
plugin: keithley
keithleys:
  - model: 6485
    auto_zero: False
    display: False
    gpib:
      url: enet://gpibid11c.esrf.fr
      pad: 22
    sensors:
      - name: pico6
        address: 1
        nplc: 0.1
        auto_range: False
	range: 2e-8
        zero_check: False
        zero_correct: False
```


* plugin name (mandatory: keithley)
* controller name (mandatory). Some controller settings are needed. To hook the
   settings to the controller we use the controller name. That is why it is
   mandatory
* controller model (optional. default: discover by asking instrument `*IDN`)
* auto-zero enabled (optional, default: False)
* display enabled (optional, default: True)
* zero-check enabled (optional, default: False). Only for 6485!
* zero-correct enabled (optional, default: False). Only for 6485!
* controller URL (mandatory, valid: gpib, tcp, serial)
    - gpib (mandatory: *url* and *pad*). See `Gpib` for
      list of options
    - serial (mandatory: *port*). See `Serial` for list
      of options
    - tcp (mandatory: *url*). See `Tcp` for list of options
* list of sensors (mandatory)
* sensor name (mandatory)
* sensor address (mandatory). Valid values:
    - model 6482: 1, 2
    - model 6485: 1
    - model 2000: 1
* sensor DC current NPLC (optional, default: 0.1)
* sensor DC current auto-range (optional, default: False)


## parameters' persistance

Some parameters (described below) are stored as settings. This means that the
static configuration described above serves as a *default configuration*.
The first time ever the system is brought to life it will read this
configuration and apply it to the settings. From now on, the keithley object
will rely on its settings. This is the same principle as it is applied on the
bliss axis velocity for example.

The following controller parameters are stored as settings:

* `auto_zero`
* `display`
* `zero_check` only for 6485
* `zero_correct` only for 6485

The following sensor parameters are stored as settings:

* `current_dc_nplc`
* `auto_range`

