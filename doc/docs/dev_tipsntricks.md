
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


## Exceptions

### capture_exceptions() context manager

`capture_exceptions()` is a context manager to capture and manage multiple
exceptions.

Usage:
```python
with capture_exceptions() as capture:
    with capture():
        do_A()
    with capture():
        do_B()
    with capture():
        do_C()
```

The inner contexts (`with capture()`) protect the execution by capturing any
exception raised. This allows the next contexts to run. When leaving the main
context (`with capture_exceptions()`), the **last** exception (potentially raised by
by `do_C()` here) is raised, if any.

If the `raise_index` argument is set to `0`, the **first** exception is raised
instead. This behavior can also be disabled by setting `raise_index` to
**None**.

The other exceptions are processed through the given excepthook, which
defaults to `sys.excepthook`.

A list containing the information about the raised exception can be
retreived using the `exception_infos` attribute of the `capture` object or
the raised exception.


Example:
```python
print("-------------------- capture_exc START ------------------")

def my_exc_handler(exc_type, exc_value, exc_traceback):
    print("     +++ FBF:", "exc_type=", exc_type,
                           "exc_value=", exc_value,
                           "exc_traceback=", exc_traceback, flush=True)


with capture_exceptions(raise_index=None, excepthook=my_exc_handler) as capture:
    with capture():
        print("try to print 123/0", flush=True)
        print(123/0)

    print("")
    with capture():
        print("try to decode a str", flush=True)
        print("ee".decode())

    if capture.failed:
        print("oh no, you cannot decode a str")
        exc_type, exc_value, exc_traceback = capture.exception_infos[-1]
        print(f"it has raised a '{exc_type}' exception")

    print("")
    with capture():
        print("try to print toto (not def)", flush=True)
        print(toto)

print("-------------------- capture_exc END ------------------", flush=True)
```

The previous example produce this (long lines are wrapped for clarity) at
execution:

`raised` is set to None so no exception is raised.

```python
-------------------- capture_exc START ------------------
try to print 123/0
     +++ FBF: exc_type= <class 'ZeroDivisionError'>
              exc_value= division by zero
              exc_traceback= <traceback object at 0x7faa58be65f0>

try to decode a str
     +++ FBF: exc_type= <class 'AttributeError'>
              exc_value= 'str' object has no attribute 'decode'
              exc_traceback= <traceback object at 0x7faa58be6230>
oh no, you cannot decode a str
it has raised a '<class 'AttributeError'>' exception

try to print toto (not def)
     +++ FBF: exc_type= <class 'NameError'>
              exc_value= name 'toto' is not defined
              exc_traceback= <traceback object at 0x7faa58c267d0>
-------------------- capture_exc END ------------------

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



## Beamline root config

To read "root beamline config", usualy located in file:  
`~/local/beamline_configuration/__init__.yml`  
such a piece of code can be used:

```python
from bliss import current_session

if current_session.config.root.get("display_initialized_objects"):
    print("bla bla")

```
