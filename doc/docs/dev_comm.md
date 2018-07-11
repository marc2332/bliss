
# Communications


## Serial line

### Controller side
Example of code to get a communication object using a serial line:

* In this example, `baudrate` is hard-coded in controller module: it cannot be changed in YML file.

        from bliss.comm.util import get_comm, SERIAL

        class Mechonics(Controller):

            def __init__(self,  *args, **kwargs):
                Controller.__init__(self, *args, **kwargs)

                # Communication
                comm_option = {'baudrate': 19200}
                self.serial = get_comm(self.config.config_dict, **comm_option)


QUESTION : openning of com / socket must be done in initialize_hardware() ?



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

### ser2net ?


### Serial line detached from a controller


pap




## TCP socket

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


## GPIB

TODO

