# BLISS shell logging

## Presentation

There are two kind of logging in Bliss:

* *Module logging*
* *Instance logging*

We can have a look at both with `lslog()`.

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
session               WARNING
session.controllers   WARNING
```

The relevant informations are:

* **module/instance** logger name that represents :
    * the module (for module loggers starting with **bliss**)
    * the instance (for instance map loggers starting with **session**)
* **level**: level name according to python standard logging levels:
    * `CRITICAL`
    * `ERROR`
    * `WARNING`
    * `INFO`
    * `DEBUG`

more info about [Python logging module](https://docs.python.org/3/library/logging.html).



### Module logging

Module-level logging is the standard python "way of logging" in which every
*logger* has the same name as the python module producing it.

The hierarchy is given by files organization inside Bliss project folder.

```python
bliss                WARNING
bliss.config         WARNING
bliss.common.mapping WARNING
bliss.scans          WARNING
bliss.shell          WARNING
bliss.standard       WARNING
```
Inside modules logger object are instantiated with the well known:
```python
import logging
logger = logging.getLogger(__name__)
```
Thiss will create a logger with a name that will be a dot separated folder/file name hierarchy.


### Instance logging

Instance-level logging allows to discriminate beetween different instances of the same class. With instance logging every device or instance has his own logger with a name that represents the conceptual hierarchy of the hardware/software stack.

```
session                                           WARNING
session.controllers                               WARNING
session.controllers.CustomMockup                  WARNING
session.controllers.CustomMockup.custom_axis      WARNING
session.controllers.FaultyMockup                  WARNING
session.controllers.FaultyMockup.bad              WARNING
session.controllers.Mockup                        WARNING
session.controllers.Mockup.hooked_error_m0        WARNING
session.controllers.Mockup.hooked_m0              WARNING
session.controllers.Mockup.hooked_m1              WARNING
session.controllers.Mockup.jogger                 WARNING
```


## Useful Commands

### Devices and instances

Activate logging can be done with global function **debugon** passing
an object or a string with a glob pattern.

```
TEST_SESSION [2]: debugon('*s1d')
Setting session.controllers.Mockup.s1d to show debug messages
TEST_SESSION [3]: debugon(m0)
Setting session.controllers.Mockup.m0 to show debug messages
```

The function **lsdebug** shows activate loggers:

```
TEST_SESSION [4]: lsdebug()

logger name                                                 level
=========================================================== ========
session.controllers.Mockup.m0                               DEBUG
session.controllers.Mockup.s1d                              DEBUG
```

Activating debug for one specific device may not give the desired
informations as a device could be managed by a controller and normally
controllers handles the communication.

Sometimes what you will probably need is to activate debug at the controller level.

```
TEST_SESSION [14]: debugon(m0.controller)
Setting session.controllers.Mockup to show debug messages
Setting session.controllers.Mockup.hooked_m0 to show debug messages
Setting session.controllers.Mockup.m2 to show debug messages
Setting session.controllers.Mockup.m0 to show debug messages
Setting session.controllers.Mockup.hooked_m1 to show debug messages
Setting session.controllers.Mockup.omega to show debug messages
Setting session.controllers.Mockup.jogger to show debug messages
Setting session.controllers.Mockup.s1f to show debug messages
Setting session.controllers.Mockup.hooked_error_m0 to show debug messages
Setting session.controllers.Mockup.s1b to show debug messages
Setting session.controllers.Mockup.s1d to show debug messages
Setting session.controllers.Mockup.m1 to show debug messages
Setting session.controllers.Mockup.s1u to show debug messages
```
or
```
TEST_SESSION [17]: debugon("*.Mockup.*")
Setting session.controllers.Mockup.hooked_m0 to show debug messages
Setting session.controllers.Mockup.m2 to show debug messages
Setting session.controllers.Mockup.m0 to show debug messages
Setting session.controllers.Mockup.hooked_m1 to show debug messages
Setting session.controllers.Mockup.omega to show debug messages
Setting session.controllers.Mockup.jogger to show debug messages
Setting session.controllers.Mockup.s1f to show debug messages
Setting session.controllers.Mockup.hooked_error_m0 to show debug messages
Setting session.controllers.Mockup.s1b to show debug messages
Setting session.controllers.Mockup.s1d to show debug messages
Setting session.controllers.Mockup.m1 to show debug messages
Setting session.controllers.Mockup.s1u to show debug messages
```

## log commands

The class instance for log commands.

### lslog()

`lslog("glob name")`

It can be used without argument to display all loggers or with a glob
pattern to apply a filter. 

Glob is the particular naming match used
usually inside linux and windows shells. The two most used wildcards
are `*` and `?` matching respectively *any number of characters* and
*one character*, but a lot more can be used (see Glob/Globbing
documentation).

Example of calling `lslog()` without argument:
```
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
session               WARNING
session.controllers   WARNING
```
Example of calling `lslog()` with a glob argument:


```
TEST_SESSION [10]: lslog('*Mock*')

logger name                                  level
============================================ ========
session.controllers.CustomMockup             WARNING
session.controllers.CustomMockup.custom_axis WARNING
session.controllers.FaultyMockup             WARNING
session.controllers.FaultyMockup.bad         WARNING
session.controllers.Mockup                   WARNING
session.controllers.Mockup.hooked_error_m0   WARNING
session.controllers.Mockup.hooked_m0         WARNING
session.controllers.Mockup.hooked_m1         WARNING
session.controllers.Mockup.jogger            WARNING
session.controllers.Mockup.m0                DEBUG
session.controllers.Mockup.m1                WARNING
session.controllers.Mockup.m2                WARNING
session.controllers.Mockup.omega             WARNING
session.controllers.Mockup.s1b               WARNING
session.controllers.Mockup.s1d               WARNING
session.controllers.Mockup.s1f               WARNING
session.controllers.Mockup.s1u               WARNING
```

### lsdebug()

`lsdebug()` shows loggers currently in debug mode:

```python
TEST_SESSION [9]: lsdebug('*Mock*')

logger name                                  level
============================================ ========
session.controllers.Mockup.m0                DEBUG
```

### debugon()

**debugon(object)** or **debugon("globname")**

Activates debug for a specific logger name using the object/alias or a glob pattern.

```python
TEST_SESSION [11]: debugon(roby)
Setting session.controllers.calc_motor_mockup.roby to show debug messages
TEST_SESSION [12]: debugoff('*m0')
Setting session.controllers.Mockup.hooked_m0 to hide debug messages
Setting session.controllers.Mockup.hooked_error_m0 to hide debug messages
Setting session.controllers.Mockup.m0 to hide debug messages
```

### debugoff()

**debugoff(object)** or **debugoff("globname")**

Like `debugon()` but sets the logging level to global defined one.

```
TEST_SESSION [13]: debugoff(roby)
Setting session.controllers.calc_motor_mockup.roby to hide debug messages
TEST_SESSION [14]: debugoff('*m0')
Setting session.controllers.Mockup.hooked_m0 to hide debug messages
Setting session.controllers.Mockup.hooked_error_m0 to hide debug messages
Setting session.controllers.Mockup.m0 to hide debug messages
```

## How to log user shell commands

It is only a matter of activating the proper logger: **bliss.shell.cli.repl**

```python
TEST_SESSION [7]: debugon('bliss.shell.cli.repl')
Setting bliss.shell.cli.repl to show debug messages
TEST_SESSION [8]: 1+2
DEBUG 2019-07-04 16:49:45,117 bliss.shell.cli.repl: USER INPUT: 1+2
         Out [8]: 3
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

debugon(roby)
debugon(m0.controller)
```

Another useful Handler is RotatingFileHandler:
```
from logging.handlers import RotatingFileHandler
# rotation of 10 log files with maximum size of 1Mb
rotatinghandler = RotatingFileHandler(‘mybliss.log’, maxBytes=1024**2, backupCount=10)
rootlogger.addHandler(rotatinghandler)  # adding the handler to the root logger
```

