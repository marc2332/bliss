
# Tips for BLISS programming


## cleanup

**cleanup context manager** feature allows to *restore parameters of objects
after the execution of code block which involves them*. Objects supporting this
functionality are:

* motors: `Axis` objects
* camera: `lima` objects

*after the execution* means:

* on a `Control-c`
* in case of exception while code is being executed
* at the normal end of the code block

Devices to consider are defined in first parameter of cleanup function.

Parameters to restore are defined in `restore_list`.

In order to deal with errors and not normal ending, `error_cleanup()` acts
similar but is executed:

* on a `Control-c`
* in case of exception while code is being executed


### Motors

For Motors, this context manager would guarantee that they will be
stopped in any case, or even returned to their initial position if
**axis.POS** is in **restore_list**.

There is the possibility to restore:

* the *velocity* (`axis.VEL`)
* the *acceleration* (`axis.ACC`)
* the *limits* (`axis.LIM`).

All motors in the context will be waited.

!!! example "Example from `bliss/common/scans.py`:"

```python
axis = enum.Enum("axis", "POS VEL ACC LIM")
```

!!! example "Usage example from `bliss/common/scans.py`:"

```python
from bliss.common.cleanup import cleanup, axis as cleanup_axis

...

with cleanup(motor, restore_list=(cleanup_axis.POS,)):
    scan = ascan(motor, start, stop, intervals, count_time, *counter_args, **kwargs)

return scan
```


## informing the user

`bliss.common.user_status_info` provides a mechanism to send information to the
user while a sequence is running.

### example

```python

from bliss.common.user_status_info import status_message
import gevent
import time

def is_finished():
    return (time.time() - t0) > 5

def my_seq():
    gevent.sleep(0.2)

t0 = time.time()

with status_message() as p:
    while(not is_finished()):
        my_seq()
        p("salut")

```


