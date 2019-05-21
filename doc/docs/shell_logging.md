# BLISS shell logging

## Presentation

There are two kind of logging in Bliss:

* *Module logging*
* *Instance logging*

We can have a look at both with `lslog()`.

```python
DEMO [2]: lslog()

BLISS MODULE LOGGERS
module               level    set
==================== ======== =====
bliss                WARNING  YES
bliss.config         WARNING  -
bliss.common.mapping WARNING  -
bliss.scans          WARNING  -
bliss.shell          WARNING  -
bliss.standard       WARNING  -

BEAMLINE INSTANCE MAP LOGGERS
instance                                          level    set
================================================= ======== =====
beamline                                          WARNING  YES
beamline.comms                                    WARNING  -
beamline.counters                                 WARNING  -
beamline.devices                                  WARNING  -
beamline.sessions                                 WARNING  -
```

The relevant informations are:

* `module` / `instance`: logger name that represents :
    * the module (for module loggers)
    * the instance (for instance map loggers)
* `level`: level name according to python standard logging levels:
    * `CRITICAL`
    * `ERROR`
    * `WARNING`
    * `INFO`
    * `DEBUG`
* set:
    * `YES` if the logging level is set for that particular level
    * `-` if the level is inherited from the upper level


more info about [Python logging module](https://docs.python.org/3/library/logging.html).



### Module logging

Module-level logging is the standard python "way of logging" in which every
*logger* has the same name as the python module producing it.

The hierarchy is given by files organization inside Bliss project folder.

```python
DEMO [2]: lslog()

BLISS MODULE LOGGERS
module               level    set
==================== ======== =====
bliss                WARNING  YES
bliss.config         WARNING  -
bliss.common.mapping WARNING  -
bliss.scans          WARNING  -
bliss.shell          WARNING  -
bliss.standard       WARNING  -

...
```
Inside modules logger object are instantiated with the well known:
```python
import logging
logger = logging.getLogger(__name__)
```
Thiss will create a logger with a name that will be a commad separated folder/file name hierarchy.


### Instance logging

Instance-level logging allows to discriminate beetween different instances of the same class. With instance logging every device or instance has his own logger with a name that represents the conceptual hierarchy of the hardware/software stack.

```
DEMO [2]: lslog()

...
BEAMLINE INSTANCE MAP LOGGERS
instance                                          level    set
================================================= ======== =====
beamline                                          WARNING  YES
beamline.comms                                    WARNING  -
beamline.counters                                 WARNING  -
beamline.devices                                  WARNING  -
beamline.devices.8d6318d7dde                      DEBUG    YES
beamline.devices.8d6318d7dde.axis.hooked_error_m0 DEBUG    -
beamline.devices.8d6318d7dde.axis.hooked_m0       DEBUG    -
beamline.devices.8d6318d7dde.axis.hooked_m1       DEBUG    -
beamline.devices.8d6318d7dde.axis.jogger          DEBUG    -
beamline.devices.8d6318d7dde.axis.m0              DEBUG    -
beamline.devices.8d6318d7dde.axis.m1              DEBUG    -
beamline.devices.8d6318d7dde.axis.m2              DEBUG    -
beamline.devices.8d6318d7dde.axis.omega           DEBUG    -
beamline.devices.8d6318d7dde.axis.roby            DEBUG    -
beamline.devices.8d6318d7dde.axis.s1b             DEBUG    -
beamline.devices.8d6318d7dde.axis.s1d             DEBUG    -
beamline.devices.8d6318d7dde.axis.s1f             DEBUG    -
beamline.devices.8d6318d7dde.axis.s1u             DEBUG    -
beamline.sessions                                 WARNING  -
```


## Useful Commands

### Devices and instances

Activate logging can be done as following:

```
TEST_SESSION [1]: debugon('*s1d')  # using glob pattern
NO bliss loggers found for [*s1d]
Set logger [beamline.devices.8d6318d713ee6be.axis.s1d] to DEBUG level
```

Or within the device itself:

```
BLISS [1]: m0 = config.get('m0')

BLISS [2]: m0._logger.debugon()

BLISS [3]: lsdebug()
NO bliss loggers for DEBUG level !!

BEAMLINE INSTANCE MAP LOGGERS
instance                             level    set
==================================== ======== =====
beamline.devices.8d6318d7dde.axis.m0 DEBUG    YES

BLISS [4]: mv(m0,2)
DEBUG 2019-05-01 beamline.devices.8d6318d7dde.axis.m0:
                        prepare_move: user_target_pos=2, relative=False

BLISS [5]: m0._logger.debugoff()

BLISS [6]: lsdebug()
NO bliss loggers for DEBUG level !!


NO map loggers for DEBUG level !!
```

Activating debug from one specific device may not give the desired
informations as a device could be managed by a controller and a
controller may handle a communication.

Sometimes what you will probably need is to activate debug from the controller level.

```
TEST_SESSION [4]: debugon('*8d6318d7*')
NO bliss loggers found for [*8d6318d7*]
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_error_m0] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m0] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m1] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.jogger] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.m0] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.m1] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.m2] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.omega] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.roby] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.s1b] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.s1d] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.s1f] to DEBUG level
Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.s1u] to DEBUG level
```

## log commands

The class instance for log commands.

### lslog()

`lslog("glob name")`

It can be used without argument to display all loggers or with a glob
pattern to apply a filter. Glob is the particular naming match used
usually inside linux and windows shells. The two most used wildcards
are `*` and `?` matching respectively 'any number of characters' and
'one character', but a lot more can be used (see Glob/Globbing
documentation).

Example of calling `lslog()` without argument:
```
BLISS [1]: lslog()
BLISS MODULE LOGGERS
module               level    set
==================== ======== =====
bliss                WARNING  YES
bliss.common.mapping WARNING  -
bliss.scans          WARNING  -
bliss.shell          WARNING  -
bliss.standard       WARNING  -



BEAMLINE INSTANCE MAP LOGGERS
instance          level    set
================= ======== =====
beamline          WARNING  YES
beamline.comms    WARNING  -
beamline.counters WARNING  -
beamline.devices  WARNING  -
beamline.sessions WARNING  -
```
Example of calling `lslog()` with a glob argument:


```
BLISS [5]: lslog('*com*')
BLISS MODULE LOGGERS
module               level    set
==================== ======== =====
bliss.common.mapping WARNING  -



BEAMLINE INSTANCE MAP LOGGERS
instance       level    set
============== ======== =====
beamline.comms WARNING  -
```

### lsdebug()

`lsdebug()` shows loggers currently in debug mode:

```python
BLISS [10]: lsdebug()
NO bliss loggers for DEBUG level !!


BEAMLINE INSTANCE MAP LOGGERS
instance          level    set
================= ======== =====
beamline.counters DEBUG    YES
```

### debugon()

```
debugon("globname")
```

Activates debug for a specific logger name using glob pattern.

```python
BLISS [22]: debugon('*hooked')
NO bliss loggers found for [hooked]
Set logger [beamline.devices.8d6318d7dde.axis.hooked_error_m0] to DEBUG level
Set logger [beamline.devices.8d6318d7dde.axis.hooked_m0] to DEBUG level
Set logger [beamline.devices.8d6318d7dde.axis.hooked_m1] to DEBUG level
```

### debugoff()

```
debugoff("globname")
```

Like `debugon()` but sets the logging level to global defined one.

```
BLISS [23]: debugoff('*hooked*')
NO bliss loggers found for [hooked]
Remove DEBUG level from logger [beamline.devices.8d6318d7de.axis.hooked_error_m0]
Remove DEBUG level from logger [beamline.devices.8d6318d7de.axis.hooked_m0]
Remove DEBUG level from logger [beamline.devices.8d6318d7de.axis.hooked_m1]
```

## How to log user shell commands

It is only a matter of activating the proper logger: bliss.shell.cli.repl

```python
BLISS [2]: debugon('bliss.shell.cli.repl')
Set logger [bliss.shell.cli.repl] to DEBUG level
NO map loggers found for [bliss.shell.cli.repl]
BLISS [3]: print('LogMe')
DEBUG 2019-05-17 13:09:32,628 bliss.shell.cli.repl: USER INPUT: print('LogMe')
LogMe
```

## Save log to File or other destinations

There are a lot of ways to accomplish this.
The easiest is to add a logging Handler to the root Logger.
This is accomplished using a normal python logging Handler taken from the standard library.

Logging could be initialized on bliss shell, but probably the best place to do this is in session configuration script.

```python
# Just near the end of your session_setup.py

from logging import getLogger, FileHandler, Formatter, DEBUG

rootlogger = getLogger()  # getting root logger
filehandler = FileHandler('mylogfile.log')  # creating a file handler
formatter = Formatter("%(asctime)s-%(name)s-%(lineno)d-%(msg)s-%(exc_info)s")  # creating a formatter for file messages
filehandler.setFormatter(formatter)  # filehandler will use the formatter
rootlogger.addHandler(filehandler)  # adding the handler to the root logger

# Just after you can set debug level for some instances

debugon('*roby')  # activating level using shell commands
roby._logger.debugon()  # alternative way of activating
```

Another useful Handler is RotatingFileHandler:
```
from logging.handlers import RotatingFileHandler
# rotation of 10 log files with maximum size of 1Mb
rotatinghandler = RotatingFileHandler(‘mybliss.log’, maxBytes=1024**2, backupCount=10)
rootlogger.addHandler(rotatinghandler)  # adding the handler to the root logger
```

