
# Communications


## Serial line

https://en.wikipedia.org/wiki/Serial_port

### Controller side
Example of code to declare a Serial line object within a controller:


        from bliss.comm.util import get_comm, SERIAL

        class Mechonics(Controller):

            def __init__(self,  *args, **kwargs):
                Controller.__init__(self, *args, **kwargs)

                # Communication
                comm_option = {'baudrate': 19200}
                self.serial = get_comm(self.config.config_dict, **comm_option)

!!! note
    In this example, `baudrate` is hard-coded in controller module: it cannot be changed in YML file.


<!-- QUESTION : openning of com / socket must be done in initialize_hardware() ??? -->
<!--  -->

### YML configuration

Example of YML configuration file to be used with previous controller:


```YAML
    -
      controller:
        class: Mechonics
        name: mechoCN30
        serial:
          url: /dev/ttyS0
        axes:
           - name: m1
             velocity: 1
             acceleration: 1
             steps_per_unit: 1
             channel: 1
```

!!! note
    `url` field is the serial device file name and the only mandatory parameter.


### Optional parameters

* `baudrate`
    * Usually in:
      1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200
    * Default: 9600

* `bytesize`
    * Default: 8

* `dsrdtr`
    * Default: False

* `interCharTimeout`
    * Default: None

* `parity`
    * Default: None

* `port`
    * Default: identic to url

* `rtscts`
    * Default: False

* `stopbits`
    * Default: 1

* `timeout`
    * Default: 5.0

* `writeTimeout`
    * Default: None

* `xonxoff`
    * Default: False


### ser2net

Ser2net (aka rfc2217) is a protocol to deport serial line via ethernet.


Such a remote serial line can be used in *rfc2217* mode or *ser2net*
mode.

*ser2net* mode allows to define the remote serial device to use in local
config (considering a well configured (with control port) ser2net
server)

*rfc2217* mode uses the mapping "port <-> serial device" defined on the
 remote host in ser2net config file

```YAML
    -
      controller:
        class: Mechonics
        name: mechoCN30
        serial:
          url: ser2net://lidXXX:29000/dev/ttyRP11
        axes:
           - name: m1
             velocity: 1
             acceleration: 1
             steps_per_unit: 1
             channel: 1
```

or:

```YAML
    -
      controller:
        class: Mechonics
        name: mechoCN30
        serial:
          url: rfc2217://lidXXX:28001
        axes:
           - name: m1
             velocity: 1
             acceleration: 1
             steps_per_unit: 1
             channel: 1
```


#### Not declared in config





### Serial line detached from a controller
Mainly for tests and debugging purpose.

#### Declared in config
To get a `ser0` object usable in a BLISS session using the `comm`
plugin.

    plugin: comm
    controller:
    - name: ser0
      serial:
        url: /dev/ttyS0


<!--   using plugin `comm` in `__init__.py` file does not work ??? -->


#### Not declared in config

Example to declare a serial line directly from a BLISS shell.

    from bliss.comm.util import get_comm, SERIAL
    
    conf = {"serial": {"url": "/dev/ttyS0"}}
    opt = {"parity": None}
    kom = get_comm(conf, ctype=SERIAL, **opt)
    print kom.write_readline("*IDN?\n")


## TCP socket

### TCP socket detached from a controller
Mainly for tests and debugging purpose.

#### Declared in config

#### Not declared in config
Example to use in BLISS shell.

    conf = {"tcp": {"url": "trucmuch.esrf.fr"}}
    opt = {"port":5025}
    kom = get_comm(conf, ctype=TCP, **opt)
    print kom.write_readline("*IDN?\n")

### Controller side
Example to get a `Socket` object:

    from bliss.comm.util import get_comm, TCP

    class Aerotech(Controller):

        def __init__(self,  *args, **kwargs):
            Controller.__init__(self, *args, **kwargs)

        def initialize(self):
            config = self.config.config_dict
            opt = {'port':8000, 'eol':'\n'}
            self._comm = get_comm(config, ctype=TCP, **opt)

other example:

    class PressureTransmitter(object):
        def __init__(self, name, config):
            self.comm = get_comm(config, baudrate=9600)


### YML configuration

Example of YML configuration file to be used with previous controller:

```YAML
  - class: aerotech
      name: Аэрофлот
      tcp:
          url: 160.103.99.42
      axes:
         - name: rot
           aero_name: X
           velocity: 10.1
           acceleration: 25.0
           steps_per_unit: 6789.444
```

### Mandatory parameters

* `url`: It can be an IP address or a fully qualified name.
    * examples:
        * `160.103.14.92`
        * `zorglub.esrf.fr`

* `port`: It's the target host's port to use.
    * example:
        * `5025`


### Optional parameters

#### port

Default:

#### timeout

Default: 5.0

#### eol

The `eol` parameter that can be defined in config or in `get_comm()`
function is used by socket to read lines. It is not sent by the
`write*()` functions and therefore a terminaison character must be
added in all messages sent to a device.

Default: `\n`


## GPIB

TODO

## UDP Socket

TODO

## SCPI

TODO

## modbus

TODO

