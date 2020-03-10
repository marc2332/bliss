# BLISS shell logging usage

## Presentation

What we normally want from Logging is obtaining information about some device or
process. This could be *more* information than usually printed on the screen or
later information, for example reading a log file.

## Log Server on Beacon

Currently the server part of bliss, Beacon, ships with a centralized log server.
This means that log messages are forwarded to Beacon and you can nicely read
them using a provided web application.

Read more about this on [Log Server](beacon_logservice.md).

## How To

- [What are basics shell logging commands?](#shell-commands)
- [I have a device that is not working properly, how to debug it?](#debug-a-device)
- [I want to start bliss with debug logging level](#start-bliss-shell-with-debug-level)
- [I need to log device when I am not present](#activate-debug-automatically)
- [I want to see what commands the user have typed](#what-user-have-typed)
- [I want to save log to file other destination (advanced)](#save-log-to-file-or-other-destinations)
- [I want to learn more about bliss kind of logging that uses a global device map](#bliss-logging-overview)
- [I want to set a logger to a specific level (not DEBUG or WARNING)](#set-logger-level)
- [I want to display only logging messages with INFO level (advanced)](#only-info-log-messages)

## Shell Commands

### debugon / debugoff

Activate logging can be done with global function `debugon()` passing an object
or a string with a glob pattern. For deactivating use instead `debugoff()`.

```python
DEMO [2]: debugon("*s1d")
Setting global.controllers.Mockup.s1d to show debug messages
DEMO [3]: debugon(m0)
Setting global.controllers.Mockup.m0 to show debug messages
```

The function **lsdebug** shows active loggers:

```python
DEMO [4]: lsdebug()

logger name                                       level
================================================= ========
global.controllers.Mockup.m0                      DEBUG
global.controllers.Mockup.s1d                     DEBUG
```

**Activating debug for one specific device may not give the desired
 informations** as a device could be managed by a controller and normally
 the controller handles the communication.

In this example we have to activate debug at the controller level like the
following:

```python
DEMO [14]: debugon(m0.controller)
Setting global.controllers.Mockup to show debug messages
Setting global.controllers.Mockup.hooked_m0 to show debug messages
Setting global.controllers.Mockup.m2 to show debug messages
Setting global.controllers.Mockup.m0 to show debug messages
Setting global.controllers.Mockup.hooked_m1 to show debug messages
Setting global.controllers.Mockup.omega to show debug messages
Setting global.controllers.Mockup.jogger to show debug messages
Setting global.controllers.Mockup.s1f to show debug messages
Setting global.controllers.Mockup.hooked_error_m0 to show debug messages
Setting global.controllers.Mockup.s1b to show debug messages
Setting global.controllers.Mockup.s1d to show debug messages
Setting global.controllers.Mockup.m1 to show debug messages
Setting global.controllers.Mockup.s1u to show debug messages
```
or with glob pattern:
```python
DEMO [17]: debugon("*.Mockup.*")
Setting global.controllers.Mockup.hooked_m0 to show debug messages
Setting global.controllers.Mockup.m2 to show debug messages
Setting global.controllers.Mockup.m0 to show debug messages
Setting global.controllers.Mockup.hooked_m1 to show debug messages
Setting global.controllers.Mockup.omega to show debug messages
Setting global.controllers.Mockup.jogger to show debug messages
Setting global.controllers.Mockup.s1f to show debug messages
Setting global.controllers.Mockup.hooked_error_m0 to show debug messages
Setting global.controllers.Mockup.s1b to show debug messages
Setting global.controllers.Mockup.s1d to show debug messages
Setting global.controllers.Mockup.m1 to show debug messages
Setting global.controllers.Mockup.s1u to show debug messages
```


### lslog

`lslog("glob name")`

It can be used without argument to display all loggers or with a glob
pattern to apply a filter.

Glob is the particular naming match used
usually inside linux and windows shells. The two most used wildcards
are `*` and `?` matching respectively *any number of characters* and
*one character*, but a lot more can be used (see Glob/Globbing
documentation).

Example of calling `lslog()` without argument:
```python
DEMO [2]: lslog()

logger name           level
===================== ========
bliss                 WARNING
bliss.common.mapping  WARNING
bliss.config.settings WARNING
bliss.scans           WARNING
bliss.shell           WARNING
bliss.shell.cli.repl  WARNING
bliss.standard        WARNING
global                WARNING
global.controllers    WARNING
```
Example of calling `lslog()` with a glob argument:


```python
DEMO [10]: lslog('*Mock*')

logger name                                  level
============================================ ========
global.controllers.CustomMockup              WARNING
global.controllers.CustomMockup.custom_axis  WARNING
global.controllers.FaultyMockup              WARNING
global.controllers.FaultyMockup.bad          WARNING
global.controllers.Mockup                    WARNING
global.controllers.Mockup.hooked_error_m0    WARNING
global.controllers.Mockup.hooked_m0          WARNING
global.controllers.Mockup.hooked_m1          WARNING
global.controllers.Mockup.jogger             WARNING
global.controllers.Mockup.m0                 DEBUG
global.controllers.Mockup.m1                 WARNING
global.controllers.Mockup.m2                 WARNING
global.controllers.Mockup.omega              WARNING
global.controllers.Mockup.s1b                WARNING
global.controllers.Mockup.s1d                WARNING
global.controllers.Mockup.s1f                WARNING
global.controllers.Mockup.s1u                WARNING
```

### lsdebug

`lsdebug()` shows loggers currently in debug mode:

```python
DEMO [9]: lsdebug('*Mock*')

logger name                                  level
============================================ ========
global.controllers.Mockup.m0                DEBUG
```


## Debug a Device

Let's say that your problematic device is the `wago_simulator`.

1. First of all be sure to have it exported to the shell using a session or
   doing `config.get('wago_simulator')`.
2. Change the logging level to debug with `debugon(wago_simulator)`.
```
TEST_SESSION [3]: debugon(wago_simulator)
Setting global.controllers.wago.Wago(wago_simulator).Engine to show debug messages
Setting global.controllers.wago.Wago(wago_simulator) to show debug messages
```
3. Do whatever operation causes problems expecting more information. Be aware
   that you can look at log messages also with the Log Viewer Web Application on
   Beacon.
```python
TEST_SESSION [4]: wago_simulator.set('o10v1',3)
DEBUG 2020-02-07 10:52:54,063 global.controllers.wago.Wago(wago_simulator).Engine: In set args=('o10v1', 3)
DEBUG 2020-02-07 10:52:54,063 global.controllers.Engine.ModbusTcp:localhost:33743: write_registers address=0 ; num=1 ; values=[63489]
DEBUG 2020-02-07 10:52:54,063 global.controllers.Engine.ModbusTcp:localhost:33743: raw_write bytes=15 b'\x00\x00\x00\x00\x00\t\xff\x10\x00\x00\x00\x01\x02\xf8\x01'
DEBUG 2020-02-07 10:52:54,064 global.controllers.Engine.ModbusTcp:localhost:33743: raw_read bytes=7 b'\x00\x00\x00\x00\x00\x06\xff'
```
4. Sometimes what you really need is to debug at a different level, for example
   if you want to debug `roby` probably you want to debug the `controller` of
   `roby`. Keep in mind this and do `debugon(roby.controller)`.
5. Than the hardest part! Try to figure out the problem... good luck!
6. At the end you can `debugoff(wago_simulator)` to turn off debug messages.


## Start bliss shell with debug level

Just launch bliss with the command line option `--log-level=DEBUG`.

This can be done also for all other levels: `CRITICAL ERROR INFO`.

## Activate Debug Automatically

If you simply `debugon` inside a Bliss shell and than restart the shell, level
will not be kept.

Let's imagine that you want to debug `roby` on `test_session`.

What you have to do is:

1. Open with an editor the setup script of the session, for example using
   `test_session` we edit the file in
   `test_configuration/sessions/test_setup.py`.
2. Add `debugon(roby)` to the setup script.
3. Level will be set automatically every time the session is started. You can
   read messages on bliss shell and on the Log Viewer Application on Beacon.

## What user have typed?

User typed commands are sent to Beacon Logserver as a default, so You can read
them using the Log Viewer Application.  You can distinguish them because they
have `user_input` inside the message, following an example:

``` 2020-02-07 10:48:38,156 test_session user_input INFO : config.get("wago_simulator")```

If you need to do something by yourself be aware that you have to operate on the logger `bliss.shell.cli.repl`.

```python
DEMO [7]: debugon('bliss.shell.cli.repl')
Setting bliss.shell.cli.repl to show debug messages
DEMO [8]: 1+2
DEBUG 2019-07-04 16:49:45,117 bliss.shell.cli.repl: USER INPUT: 1+2
         Out [8]: 3
```

## Save log to file or other destinations

**NOTE:** This example is somehow outdated by the existance of Beacon Log
Services that centralize and automatically log to file, but could be still
useful to learn how to manipulate loggers to accomplish advanced tasks.

There are a lot of ways to accomplish this.
The easiest is to add a logging Handler to the root Logger.
This is accomplished using a normal python logging Handler taken from the
standard library.

Logging could be initialized in the BLISS shell, but probably the best place to
do this is in th session configuration script.

```python
# Just near the end of the session_setup.py file.

from logging import getLogger, FileHandler, Formatter, DEBUG

rootlogger = getLogger()  # getting root logger

# creating a file handler
filehandler = FileHandler('mylogfile.log')

# creating a formatter for the file messages
formatter = Formatter("%(asctime)s-%(name)s-%(lineno)d-%(msg)s-%(exc_info)s")

filehandler.setFormatter(formatter)  # filehandler will use the formatter

rootlogger.addHandler(filehandler)  # adding the handler to the root logger

# Just after you can set debug level for some instances

debugon(roby)
debugon(m0.controller)
```

Another useful Handler is `RotatingFileHandler`:
```python
from logging.handlers import RotatingFileHandler

# rotation of 10 log files with maximum size of 1Mb
rotatinghandler = RotatingFileHandler(‘mybliss.log’,
                                      maxBytes=1024**2,
                                      backupCount=10)

# adding the handler to the root logger
rootlogger.addHandler(rotatinghandler)
```

## Set Logger Level

Bliss shell commands `debugon` and `debugoff` normally switch between WARNING
and DEBUG logging levels.

If you need to use another level here is how to do it:

```python
TEST_SESSION [16]: import logging
TEST_SESSION [17]: get_logger(m0).setLevel(logging.INFO)
```

As you can see we first get the logger using the instance `m0`, than we set the
level, in this case to logging.INFO.

## Only info log messages

We will add a filter to our root logger to stop all messages that are not of level INFO.

Let's do it:

```python
TEST_SESSION [1]: import logging
TEST_SESSION [2]: def filter_(msg):
             ...:     if msg.levelno == logging.INFO:
             ...:         return True
             ...:     return False
TEST_SESSION [3]: rootlogger = logging.getLogger()  # getting root logger
TEST_SESSION [4]: rootlogger.handlers
         Out [4]: [<StreamHandler <stderr> (DEBUG)>, <NoGreenletSocketHandler (DEBUG)>]

TEST_SESSION [5]: for handler in rootlogger.handlers:
             ...:     handler.addFilter(filter_)
TEST_SESSION [6]: # now we `debugon` star to let all loggers forward messages to handlers
TEST_SESSION [7]: debugon('*')
Setting global.controllers.Mockup.hooked_m1 to show debug messages
Setting global.controllers.calc_motor_mockup.calc_mot1 to show debug messages
Setting bliss.logbook_print to show debug messages
Setting exceptions to show debug messages
... omissis ...

TEST_SESSION [8]: get_logger(m0).info("this will be shown")  # emulating a log message forwarded by m0
INFO 2020-02-07 14:19:46,289 global.controllers.Mockup.m0: this will be shown
TEST_SESSION [9]: get_logger(m0).error("this will not show")
```

## Bliss Logging Overview

We can say that Bliss uses two kinds of logging naming:

* *Module logging*
* *Instance logging*

We can have a look at both with `lslog()`, here is the result of the command
given to an empty session.

```python
BLISS [1]: lslog()

logger name           level
===================== ========
bliss                 WARNING
bliss.common.mapping  WARNING
bliss.config.settings WARNING
bliss.logbook_print   INFO
bliss.scans           WARNING
bliss.shell           WARNING
bliss.shell.cli.repl  WARNING
bliss.shell.standard  WARNING
flint                 WARNING
flint.output          INFO [DISABLED]
global                WARNING
global.controllers    WARNING
```

The relevant information is:

* **module/instance** logger name that represents :
    * the module (for module loggers starting with **bliss**)
    * the instance (for instance map loggers starting with **session**)
* **level**: level name according to python standard logging levels:
    * `CRITICAL`
    * `ERROR`
    * `WARNING`
    * `INFO`
    * `DEBUG`

More info about [Python logging module](https://docs.python.org/3/library/logging.html).


### Module logging

Module-level logging is the standard python "way of logging" in which every
*logger* has the same name as the python module producing it.

The hierarchy is given by the file organization inside BLISS project folder.

```python
bliss                WARNING
bliss.config         WARNING
bliss.common.mapping WARNING
bliss.scans          WARNING
bliss.shell          WARNING
bliss.standard       WARNING
```
Inside modules, logger object are instantiated with the well known:
```python
import logging
logger = logging.getLogger(__name__)
```

This will create a logger with a name that will be a dot separated folder/file
name hierarchy.


### Instance logging

Instance-level logging allows to discriminate beetween different instances of
the same class. With instance logging every device or instance has his own
logger with a name that represents the conceptual hierarchy of the
hardware/software stack.

```
global                                            WARNING
global.controllers                                WARNING
global.controllers.CustomMockup                   WARNING
global.controllers.CustomMockup.custom_axis       WARNING
global.controllers.FaultyMockup                   WARNING
global.controllers.FaultyMockup.bad               WARNING
global.controllers.Mockup                         WARNING
global.controllers.Mockup.hooked_error_m0         WARNING
global.controllers.Mockup.hooked_m0               WARNING
global.controllers.Mockup.hooked_m1               WARNING
global.controllers.Mockup.jogger                  WARNING
```

Instance logging rely on bliss `global_map` that is a map of instances
made at runtime.
Read more information at [Bliss Device Map](dev_instance_map.md)
