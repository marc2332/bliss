# Writing a BLISS controller

Here you can find somt tips about the wrinting of a BLISS controller.

## @autocomplete_property decorator

In many controllers, the `@property` decorator is heavily used to protect certain
attributes of the instance or to limit the access to read-only. When using the
bliss command line interface the autocompletion will **not** suggeste any
completion based on the return value of the method underneath the property.

This is a wanted behavior e.g. in case this would trigger hardware
communication. There are however also usecases where a *deeper* autocompletion
is wanted.

!!! note
     "↹" represents the action of pressing the "Tab" key of the keyboard.

Example: the `.counter` namespace of a controller. If implemented as
`@property`:
```
BLISS [1]: lima_simulator.counters. ↹
```

Would not show any autocompletion suggestions. To enable *deeper* autocompletion
a special decorator called `@autocomplete_property` must be used.
```python
from bliss.common.utils import autocomplete_property

class Lima(object):
    @autocomplete_property
    def counters(self):
        all_counters = [self.image]
        ...
```

Using this decorator would result in autocompletion suggestions:
```
BLISS [1]: lima_simulator.counters. ↹
                                   _roi1_
                                   _roi2_
                                   _bpm_
```

## The `__info__()` method for Bliss shell

!!! info

    - Any Bliss controller that is visible to the user in the command line
      should have an `__info__()` function implemented!
    - The return type of `__info__()` must be `str`, otherwhise it fails and
      `__repr__()` is used as fallback!
    - As a rule of thumb: the return value of a custom `__repr__()` implementation
      should not contain `\n` and should be inspired by the standard
      implementation of `__repr__()` in python.

In Bliss, `__info__()` is used by the command line interface (Bliss shell or Bliss
repl) to enquire information of the internal state of any object / controller in
case it is available.

This is used to have simple way to get (detailed) information that is needed
from a **user point of view** to use the object. This is in contrast to the
build-in python function `__repr__()`, which should return a short summary of the
concerned object from the **developer point of view**. The Protocol that is put
in place in the Bliss shell is the following:

* if the return value of a statement entered into the Bliss shel is a python
  object with `__info__()` implemented this `__info__()` function will be called
  by the Bliss shell to display the output. As a fallback option (`__info__()`
  not implemented) the standard behavior of the interactive python interpreter
  involving `__repr__` is used. (For details about `__repr__` see next section.)

Here is an example for the lima controller that is using `__info__`:
```
LIMA_TEST_SESSION [3]: lima_simulator
              Out [3]: Simulator - Generator (Simulator) - Lima Simulator
                       
                       Image:
                       bin = [1 1]
                       flip = [False False]
                       height = 1024
                       roi = <0,0> <1024 x 1024>
                       rotation = rotation_enum.NONE
                       sizes = [   0    4 1024 1024]
                       type = Bpp32
                       width = 1024
                       
                       Acquisition:
                       expo_time = 1.0
                       mode = mode_enum.SINGLE
                       nb_frames = 1
                       status = Ready
                       status_fault_error = No error
                       trigger_mode = trigger_mode_enum.INTERNAL_TRIGGER
                       
                       ROI Counters:
                       [default]
                       
                       Name  ROI (<X, Y> <W x H>)
                       ----  ------------------
                         r1  <0, 0> <100 x 200>
```

The information given above is usefull from a **user point of view**. As a
**developer** one might want to work in the Bliss shell with live object e.g.

```python
LIMA [4]: my_detectors = {'my_lima':lima_simulator,'my_mca':simu1}
LIMA [5]: my_detectors
 Out [5]: {'my_lima': <Lima Controller for Simulator (Lima Simulator)>,
                        'my_mca': <bliss.controllers.mca.simulation.SimulatedMCA
                                   object at 0x7f2f535b5f60>}
```

In this case it is desirable that the python objects themselves are clearly
represented, which is exactly the role of `__repr__` (in this example the
`lima_simulator` has a custom `__repr__` while in `simu1` there is no `__repr__`
implemented so the bulid in python implementation is used).

The signature of `__info__()` should be `def __info__(self):` the return value
must be a string.

```python
BLISS [1]: class A(object):
      ...:     def __repr__(self):
      ...:         return "my repl"
      ...:     def __str__(self):
      ...:         return "my str"
      ...:     def __info__(self):
      ...:         return "my info"

BLISS [2]: a=A()

BLISS [3]: a
  Out [3]: my info

BLISS [4]: [a]
  Out [4]: [my repl]
```

!!! warning

    If, for any reason, there is an exception raised inside `__info__`, the
    fallback option will be used and `__repr__` is evaluated in this case.

    And **this will hide the error**. So, *any* error musst be treated
    before returning.


Example of a typical implementation of `.__info__()` method (no more need of
exception management like previously):
```python

def __info__(self):
    """Standard method called by BLISS Shell info helper."""
    info_str = ""
    info_str += " bla bla\n"

    return info_str
```

The equivalent of `repr(obj)` or `str(obj)` is also availabe in
`bliss.shell.standard` as `info(obj)` which can be used also outside the Bliss
shell.

```
Python 3.7.3 (default, Mar 27 2019, 22:11:17)
[GCC 7.3.0] :: Anaconda, Inc. on linux
Type "help", "copyright", "credits" or "license" for more information.

>>> from bliss.shell.standard import info

>>> class A(object):
...     def __repr__(self):
...          return "my repl"
...     def __info__(self):
...          return "my info"
...
>>> info(A())
'my info'

>>> class B(object):
...     def __repr__(self):
...          return "my repl"
...

>>> info(B())
'my repl'
```

## `__str__()` and `__repr__()`

If implemented in a Python class, `__repr__` and `__str__` methods are
build-in functions Python to return information about an object instantiating this class.

* `__str__` should print a readable message
* `__repr__` should print a __short__ message obout the objec that is unambigous (e.g. name of an identifier, class name, etc).

* `__str__` is called:
    - when the object is passed to the print() function (e.g. `print(my_obj)`).
    - wheh the object is used in string operations (e.g. `str(my_obj)` or
      `'{}'.format(my_obj)` or `f'some text {my_obj}'`)
* `__repr__` method is called:
    - when user type the name of the object in an interpreter session (a python
      shell).
    - when displaying containers like lists and dicts (the result of `__repr__`
      is used to represent the objects they contain)
    - when explicitly asking for it in the print() function. (e.g. `print("%r" % my_object)`)


By default when no `__str__` or `__repr__` methods are defined, the `__repr__`
returns the name of the class (Length) and `__str__` calls `__repr__`.



