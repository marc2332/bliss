# Adding logging and mapping capabilities to Controller

To know how to use logging inside the shell, see: [Shell Logging](shell_logging.md)

To know more about mapping and how to use it, see: [Session map](dev_instance_map.md)

## Summary

To log or to print something in a controller, there are three sets of functions
that can be choosen depending on the intended destination of the message to be
logged or printed:

* [log_debug, log_warning, ...](dev_maplog_controller.md#log_debug-log_info)
  send to Beacon (subject to `debugon`/`debugoff`)
* [user_print, user_warning, ...](dev_maplog_controller.md#user_debug-user_info)
  show the user (subject to `disable_user_output`)
* [elog_print, elog_warning, ...](dev_maplog_controller.md#elog_debug-elog_info)
  send to the electronic logbook (not subjected to anything)

Most of the time, `user_print()` should be used in place of `print()` because
the "user" is not necessarily stdout.

When it concerns a warning or error message however, using `user_warning()` or
`user_error()` instead must be considered.


## Logging and Mapping

*Logging* and *Mapping* instances are strictly related in Bliss: every instance
should be registered to the *session map* before gaining *logging features*.

## How to Register an instance

```python
from bliss.common.logtools import *
from bliss import global_map

class MyController:
    def __init__(self, *args, **kwargs):
        self.comm = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        global_map.register(self, children_list=[comm], tag=self.name)
        ...
        log_info(self, "HI, I am born")
```

The preceding is a barebone example of how to register an instance inside
the global map and send an INFO logging message.

### Register the device/instance to the map

```python
global_map.register(self, children_list=[comm], tag=self.name)
```

This code will add the instance to the device map of the session.

See how socket are created and registered as a child of `MyController`.

!!!note

    This single operation will register both instances (`MyController` as `self` and
    the socket) to the map putting in place the hierarchical relation beetween them.

A **tag** can be assigned to better visualize nodes in the map and in the log
hierarchy. If not, the library will try its best to assign a proper name anyway.

!!!note

    Notice also that if instance is not registered to the map the
    first call to a `log_` method will do it automatically.


## How to Create a session map

The **map** is in fact a Graph that wants to register every relevant
instance of a Session, including: Controller, Connections, Devices,
Axis, and so on.

When registering an instance, it is convenient to add as much information as
possible in order to use them later for visualizing or to apply any sort of
elaboration.

For this reason is important to add:

* `parents_list`: a list containing the parents of the instance, in case
  of a device it will be the controller instance, in case of a
  communication it will be a controller but also "comms".
  If no parent is specify for a node it will have `controllers` as default parent.
* `children_list`: a list containing children istances as comms,
  transactions, devices, axis
* `tag`: this should be the best suited name to represent the instance, if not
  given instance name, class or id will be used.


### Example 1:

Here is a Motor that is child of a controller:

```python
# imagine this code inside an Axis.axis class
# in this specific example we have instantiated m0
# 'name' attribute is used as default to represent the object in the map
# 'tag' can be passed as kwarg to replace the name
# default is using name attribute of class
global_map.register(self, parents_list=[self.controller])
```

{% dot session_map_basic.svg
  digraph  {
    rankdir="LR";

    controller [label="ee6beb9efb",];
    axis [label="m0"]
    controller -> axis;
    controllers -> controller;
    session -> controllers:w;
    session -> comms;
    session -> counters:w;
  }
%}

### Example 2:

Here is a controller with a child connection:
```python
# self is test_controller
global_map.register(self, children_list=[self._cnx], tag='test controller')
```

{% dot session_map_basic.svg
  digraph  {
    rankdir="LR";

    controller [label="test controller",];
    conn [label="tcp_ip"]
    controller -> conn;
    controllers -> controller;
	session -> controllers:w;
	session -> comms;
	session -> counters:w;
}
%}

### Example 3:

Here is a TCP connection that we also want to be child of
`session->comms`

```python
# during the first passage we register m0 and the controller
global_map.register(m0, parent_list=[m0.controller])
# during the second passage we register the TCP connection as a child of
# m0 and of comms
global_map.register(m0.conn, parent_list=[m0.controller, 'comms'])
```

{% dot session_map_basic.svg
  digraph  {
    rankdir="LR";
	session -> controllers:w;
	session -> comms;
	session -> counters:w;
    controllers -> controller;
    controller -> m0;
    controller -> tcp;
    comms -> tcp;
  }
%}
### Example 4:

To explain the flexibility here we are registering a child socket `self._fd`
inside a Command class (self).
If no parent is provided instances are registered under *controllers* as default.

If parent is provided later (or if this instance is a child of another one) the map
will take this into account and remap nodes automatically.


```python
from bliss import global_map

self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
global_map.register(self._fd, parents_list=[self, "comms"],
                    tag=f"Socket[{local_host}:{local_port}",
```

{% dot devices_mapping.svg
  digraph devices_mapping{
    rankdir="LR";

    session -> controllers:w;
    session -> comms;
    session -> counters:w;
    controllers -> command;
    sock [label="Socket\n[localhost:47319]"];
    command:e -> sock;
    comms:e -> sock;
  }
%}

### Final Considerations

There is no problem to register the same instance twice or
even more times: it will automatically remap adding or removing links
if necessary.

In general this is convenient for example to log as soon as possible and then
after creating, let's say a Socket, to register it as a child.

The Bliss barebone map is something like this:

{% dot session_map_basic.svg
  digraph {
	session -> controllers;
	session -> comms;
	session -> counters;
	session -> axes;
}
%}

Those string-type graph nodes provide the skeleton to which all other nodes are
attached.

More string-type nodes an be created as a user if needed.

!!!warning
    Be aware that all instances, if nothing is specify, will be child of
    "controllers".


## Using the logtools

Bliss provides a `BlissLogger` for instances/devices that gives some additional
power.

Normally no-one need to care about this except to use some more functionalities
in respect to normal Python `logging.Logger(__name__)`.

This is how to proceed to add logging and printing to a controller:

1. Import `logtools`:
    `from bliss.common.logtools import log_XXX`
2. Logging utility functions to send messages to Beacon and the user:
    * `log_debug()` `log_debug_data()`
    * `log_info()` `log_warning()` `log_error()` `log_critical()` `log_exception()`
3. Configure the logging utility functions above:
    * `get_logger()`
    * `set_log_format()`
    * `hexify()` `asciify()`
4. Send messages to the user:
    * `user_debug()` `user_info()` `user_warning()` `user_error()` `user_critical()`
    * `user_print()` `disable_user_output()`
5. Send messages to the electronic logbook:
    * `elog_debug()` `elog_info()` `elog_warning()` `elog_error()`
    * `elog_critical()` `elog_print()`


### log_debug, log_info, ...

Use them to log messages to a specific level, always pass as first argument the
instance (normally self).

```python
log_debug(self, "ACK received from %s" , host)
log_error(self, "Connection Failed")

# use after an except to add exception info
log_exception(self, "No response after %d times", n_retry)
```

As normal python logging methods `%-string` formatting (similar to `C` language
`printf`) should be used. The use of python `f-strings` is discouraged as is not
a lazy evaluation.

### log_debug_data

Like `log_debug()` but has an additional argument `(data)`. This argument should
be the last after eventual `%-string` arguments.

The idea in mind was to provide a debug function specifically for debugging
**raw data** like low communication layers.

This function format the data in a nice way and allow to change
dynamically the kind of visualization for `string` and `bytestring`.


```python
DEMO [17]: from bliss import global_map

DEMO [18]: global_map.register('fakenode')  # register this fake string node

DEMO [19]: debugon('*fakenode')
Setting session.controllers.fakenode to show debug messages

DEMO [20]: log_debug_data('fakenode', "Received data from %s", host, b'13$213')
session.controllers.fakenode: Received data from 192.168.3.20 bytes=6 b'13$213'

DEMO [21]: set_log_format('fakenode','hex')

DEMO [22]: log_debug_data('fakenode', "Received data from %s", host, b'13$213')
session.controllers.fakenode: Received data from 192.168.3.20
                              bytes=6 \x31\x33\x24\x32\x31\x33

```

Use `set_log_format(instance, "ascii")` or `set_log_format_(instance, "hex")` to
change the format of log_debug_data messages.

The same kind of formatting can be obtained directly in code with `hexify()` and
`asciify()`:

```python
DEMO [32]: asciify(bytes([i for i in range(0,100)]))
 Out [32]: b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11
             \x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !"#$%&\'()
             *+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abc'

DEMO [33]: hexify(bytes([i for i in range(0,100)]))
   Out [33]: '\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07\\x08\\x09\\x0a\\x0b\\x0c
   \\x0d\\x0e\\x0f\\x10\\x11\\x12\\x13\\x14\\x15\\x16\\x17\\x18\\x19\\x1a\\x1b
   \\x1c\\x1d\\x1e\\x1f\\x20\\x21\\x22\\x23\\x24\\x25\\x26\\x27\\x28\\x29\\x2a
   \\x2b\\x2c\\x2d\\x2e\\x2f\\x30\\x31\\x32\\x33\\x34\\x35\\x36\\x37\\x38\\x39
   \\x3a\\x3b\\x3c\\x3d\\x3e\\x3f\\x40\\x41\\x42\\x43\\x44\\x45\\x46\\x47\\x48
   \\x49\\x4a\\x4b\\x4c\\x4d\\x4e\\x4f\\x50\\x51\\x52\\x53\\x54\\x55\\x56\\x57
   \\x58\\x59\\x5a\\x5b\\x5c\\x5d\\x5e\\x5f\\x60\\x61\\x62\\x63'
```

### debugon() and debugoff()

These methods are available in the [shell](shell_logging.md#debugon-debugoff).
They allow setting the logging level to DEBUG or reset to default level.

Example:
```python
from socket import *
class MyController:
    def __init__(self, *args, **kwargs):
        self.comm = socket(AF_INET, SOCK_STREAM)
        global_map.register(self, children_list=[self.comm])
        # debug kept on while writing/debugging the controller.
        debugon(self)
        log_debug(self, "HI, I am born")
        self.worked_times = 0

    def work(self):
        log_debug_data(self, 'I am working a lot', self.worked_times)
```

```python
DEMO [61]: mycon = MyController()
Setting session.controllers.MyController.socket to show debug messages
Setting session.controllers.MyController to show debug messages

DEBUG 2019-07-05 09:38:26,164 session.controllers.MyController: HI, I am born

DEMO [62]: debugoff(mycon)  # use debugon/off from shell also!
Setting session.controllers.MyController.socket to hide debug messages
Setting session.controllers.MyController to hide debug messages

DEMO [63]: mycon.work()  # nothing shows
```

### user_debug, user_info, ...

Instead of using `print()` to show a message to the user, the command
`user_print()` should be used. This allows output to be disabled in a context
manager:

```python
with disable_user_output():
    for axis in axes_list:
        axis.hw_limit(limit, wait=False)
```

In addition there are the functions `user_debug()`, `user_info()`,
`user_warning()` and `user_error()` which decorate the message with a level
prefix.

As opposed to `user_print()`, these functions are subject to the log level of
`bliss.common.logtools.userlogger` (NOTSET by default).

### elog_debug, elog_info, ...

The user can use [elog_print](shell_std_func.md#elog_print) and
[elog_add](shell_std_func.md#elog_add) to send "comments" to the logbook.

In addition there are the functions `elog_debug()`, `elog_info()`,
`elog_warning()` and `elog_error()` which send level notifications to the
electronic logbook.

As opposed to `elog_print()`, these functions are subject to the log level of
`bliss.common.logtools.elogbook` (NOTSET by default).

The function `elog_command()` can be used to log the execution of a particular
function.

## More complex example

First defining a class MyConnection:

```python
class MyConnection:
    def __init__(self, address):
        log_debug(self, "In %s.__init__", type(self))
        self.address = address
        self.sock = socket(AF_INET, SOCK_STREAM)
        global_map.register(self, children_list=[self.sock])
        log_debug(self, "Myconnection socket created to %s", address)

    def send(self):
        self.sock.connect((self.address,80))
        self.sock.send(b'GET /\n\r\n\r')
        data = self.sock.recv(1024)
        log_debug_data(self.sock, "Received from %s", self.address, data)
```
Then define a controller that uses MyConnection:

```python
class MyController:
    def __init__(self, *args, **kwargs):
        self.comm = MyConnection("www.google.com")
        global_map.register(self, children_list=[self.comm])
        # debug kept on while writing/debugging the controller.
        debugon(self)
        log_debug(self, "HI, I am born")
        self.worked_times = 0

    def work(self):
        self.comm.send()
```

And than burn powder!

```python
DEMO [96]: mycontroller = MyController()
Setting session.ctrlers.MyController to show debug messages
Setting session.ctrlers.MyController.MyConnection.socket to show debug messages
Setting session.ctrlers.MyController.MyConnection to show debug messages
Setting session.ctrlers.MyController.socket to show debug messages
DEBUG 2019-07-05 10:00:00,000 session.controllers.MyController: HI, I am born

DEMO [97]: mycontroller.work()
DEBUG 2019-07-05 10:00:08 session.controllers.MyController.MyConnection.socket:
 Received from www.google.com bytes=547 b'HTTP/1.1 301 Moved Permanently\r\n
 Location: http://www.google.com/\r\nContent-Type: text/html; charset=UTF-8\r\n
 Date: Fri, 05 Jul 2019 07:59 GMT\r\nExpires: Sun, 04 Aug 2019 07:59 GMT\r\n
 Cache-Control: public,
 max-age=25920\r\nServer: gws\r\nContent-Length: 219\r\nX-XSS-Protection: 0\r\n
 X-Frame-Options: SAMEORIGIN\r\nConnection: close\r\n\r\n<HTML><HEAD>
 <meta http-equiv="content-type" content="text/html;charset=utf-8">\n
 <TITLE>301 Moved</TITLE></HEAD><BODY>\n<H1>301 Moved</H1>\n
 The document has moved\n <A HREF="http://www.google.com/">here</A>.\r\n
 </BODY></HTML>\r\n'

DEMO [98]: debugoff(mycontroller)
Setting session.ctrlers.MyController to hide debug messages
Setting session.ctrlers.MyController.MyConnection.socket to hide debug messages
Setting session.ctrlers.MyController.MyConnection to hide debug messages
Setting session.ctrlers.MyController.socket to hide debug messages

DEMO [99]: mycontroller.work()
DEMO [100]:
```
