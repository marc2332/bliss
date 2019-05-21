# Adding logging and mapping capabilities to Controller


To know how to use logging inside the shell, see: [Shell Logging](shell_logging.md)

To know more about mapping and how to use it, see: [Session map](dev_instance_map.md)

## Logging and Mapping

Logging and Mapping instances are strictly related in Bliss: every
instance should register himself before gaining those features.

## How to Register an instance

```python
from bliss.common import session
from bliss.common.logtools import LogMixin

class MyController(LogMixin):
    def __init__(self, *args, **kwargs):
        session.get_current().map.register(self)
        ...
        self._logger.info("HI, I am born")
```

The preceding is a barebone example of how to register an instance inside
session map and send an INFO logging message.

Key points are the following:

### Add LogMixin to the class

This will add `_logger` method to class that will be the entry point for
all logging operations and will also raise an exception if the logging
will be used before instance is mapped inside bliss session map.

### Register the instance

This is done calling `session.get_current().map.register` passing at list the self
parameter. If _logger methods are used before the registration this
will fail raising an exception; for this reason mapping.register
should be called as soon as possible.

## How to Create a nice session map

The map is in fact a Graph that wants to register every relevant
instance of a Session, including Controller, Connections, Devices,
Axis, and so on.

When registering an instance it is convenient to add as much information
as possible in order to have an usefull map that can be used to
represent the session or to apply any sort of desired handler.

For this reason is important to add:

* parents_list: a list containing the parents of the instance, in case
  of a device it will be the controller instance, in case of a
  communication it will be a controller but also "comms".
* children_list: a list containing children istances as comms,
  transactions, devices, axis
* tag: this should be the best suited name to represent the instance, if not
       given instance.name will be used or id of the object

Some Examples:

### Example 1:

Here we have a Motor that is child of a controller
```python
# self is motor instance (we are inside Axis.axis class)
# 'name' attribute is used as default to represent the object in the map
# 'tag' can be passed as kwarg to replace the name
# default is using name attribute of class
m = session.get_current().map
m.register(self, parents_list=[self.controller])
```

{% dot session_map_basic.svg
strict digraph  {
  rankdir="LR";
  splines=false;

	session;
	controllers;
  controller [label="ee6beb9efb",];
  axis [label="m0"]
  controller -> axis;
  controllers -> controller;
	session -> controllers;
	comms;
	session -> comms;
	counters;
	session -> counters;
}
%}
### Example 2:

Here we have a controller with a child connection
```python
# self is test_controller
m = session.get_current().map
m.register(self, children_list=[self._cnx], tag='test controller')
```
{% dot session_map_basic.svg
strict digraph  {
  rankdir="LR";
  splines=false;

	session;
	controllers;
  controller [label="test controller",];
  conn [label="tcp_ip"]
  controller -> conn;
  controllers -> controller;
	session -> controllers;
	comms;
	session -> comms;
	counters;
	session -> counters;
}
%}
### Example 3:

Here we have a serial connection that we also want to be child of
"session"->"comms"

```python
# registering m0, this normally is automatic, just as an example
# first passage we register m0, the controller and the connection
m = session.get_current().map
m.register(m0, parent_list=[m0.controller])
# in the second passage we register the TCP connection as a child of
# m0 and of comms
m = session.get_current().map
m.register(m0.conn, parent_list=[m0.controller, 'comms'])
```

{% dot session_map_basic.svg
strict digraph  {
  rankdir="LR";
  splines=false;

	session;
	controllers;
	session -> controllers;
	comms;
	session -> comms;
	counters;
	session -> counters;
  controller;
  controllers -> controller;
  m0;
  controller -> m0;
  tcp;
  controller -> tcp;
  comms -> tcp;

}
%}
### Example 4:

To explain the flexibility here we are mapping inside a Command class
(that is self) and `self._fd` is a child socket, in fact we are inside
Command but we are recording all links beetween them. The result will
something like this:



In fact, instances that will not have parents will be childs of
"session"->"controllers" by default and later eventually remapped if we
register another instance as parent of `Command`.

```python
from bliss.common import session
m = session.get_current().map

self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
m.register(self._fd, parents_list=[self, "comms"], tag=f"Socket[{local_host}:{local_port}",
```
{% dot devices_mapping.svg
  digraph devices_mapping{
  rankdir="LR";
  splines=false;

  session;
  controllers;
  session -> controllers;
  comms;
  session -> comms;
  counters;
  session -> counters;
  command;
  controllers -> command;
  sock [label="Socket[localhost:47319]"];
  command -> sock;
  comms -> sock;

  }
%}

### Final Considerations:

There is no problem if you want to register the same instance twice or
even more times: it will automatically remap adding or removing links
if necessary.  In general this is convenient for example when you want
to log as soon as possible and then after creating let's say a Socket
you want to register it a child.

The Bliss barebone map is something like this:

{% dot session_map_basic.svg
strict digraph  {
	node [label="\N"];
	session;
	controllers;'
	session -> controllers;
	comms;
	session -> comms;
	counters;
	session -> counters;
}
%}

Those Graph nodes are in fact string and they constitute the root to
wich all other nodes will be attached.

Be aware that all instances, if nothing is specify, will be child of
controllers.


## Logging Instance Methods

Every instance that inherits from LogMixin and is registered gains a _logger instance that is in fact a python logging.Logger instance with some more powers.

This means that you will find a ._logger attribute attached to your instance that you can use to send messages and configure logging.

The most useful methods are:

    * .debugon()
    * .debugoff()
    * .debug_data(message, data)
    * .set_ascii_format()
    * .set_hex_format()

### .debugon() and .debugoff()

Simply to set logging level to DEBUG or reset to default level.

### .debug_data, .set_ascii_format, .set_hex_format

The purpose of debug_data is to have a convenient way to debug aggregate data like string, bytestrings and dictionary. This is helpful for hardware comunication.

The first argument of debug_data is the user-readable message, the second is a string, bytestring or a dictionary.

set_ascii_format and set_hex_format methods allows to change the representation of data at runtime.

Let's do some examples:

### Passing a dictionary to debug_data:

```python

T_SESSION [14]: m0._logger.debug_data('Machine connection settings',{'ip':'10.81.0.23','hostname':'wcid00b'})
DEBUG 2019-05-17 14:58:27,861 session.controllers.8d6318d713.axis.m0: Machine connection settings ip=10.81.0.23 ; hostname=wcid00b
```

### Simulating a message sent from `m0`.
Check how debug_data works and how we can change format from ascii to hex and viceversa, this can be done at runtime.

```python
TEST_SESSION [1]: m0._logger.debugon()
TEST_SESSION [2]: raw_msg = bytes([0,2,3,12,254,255,232,121,123,83,72])
TEST_SESSION [3]: m0._logger.set_ascii_format()
TEST_SESSION [4]: m0._logger.debug_data('Sending Data',raw_msg)
DEBUG 2019-05-17 15:24:26,231 session.controllers.8d6318d.axis.m0: Sending Data bytes=11 b'\x00\x02\x03\x0c\xfe\xff\xe8y{SH'
TEST_SESSION [5]: m0._logger.set_hex_format()
TEST_SESSION [6]: m0._logger.debug_data('Sending Data',raw_msg)
DEBUG 2019-05-17 15:24:34,731 session.controllers.8d6318d.axis.m0: Sending Data bytes=11 \x00\x02\x03\x0c\xfe\xff\xe8\x79\x7b\x53\x48
```
