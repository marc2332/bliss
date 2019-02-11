# Beacon settings

*Beacon settings* are helper classes to store data in the Redis database at
runtime from Python code, using BLISS.

Use cases for settings:

* on top of static configuration parameters
    - motor velocity, acceleration, limits
    - auto-gain on a Keithley
* to keep (or share) information across executions (or across processes)
    - selected counter for plot
    - enabled loggers, log level
    - scan saving path, file template...

## Settings classes

BLISS provides different classes for different kinds of settings.

### SimpleSetting

The `SimpleSetting` class is used to save a *scalar value*:

* int
* float
* string
* bool

Example:

```py
from bliss.config import settings
magicNumber = 63825363
iii = settings.SimpleSetting('myIntkey', default_value=magicNumber)
assert iii.get() == magicNumber
iii.set(42)
assert iii.get() == 42
assert isinstance(iii.get(), int)
```

The `default_value` is returned by the `SimpleSetting` object until it has been
set. Once the object has been set, the value is persisted in redis.

### HashSetting

The `HashSetting` class is used to represent a dictionary of scalar values:

```py
myDict = {"C1":"riri", "C2":"fifi"}
shs = settings.HashSetting('myHkey', default_values=myDict)  # note the s :)
```

### QueueSetting

The `QueueSetting` class is used to represent a list of scalar values:

```py
>>> myList = ["a", "b", "c", "d"]
>>> sqs = settings.QueueSetting('myQkey')
>>> sqs.set(myList)
```

### Parameters

`Parameters` are more advanced objects -- it is used to group
simple settings, and to be able to switch from one set of values for
the parameters to another:

```py
>>> from bliss.config.settings import Parameters
>>> p = Parameters("my_params")
>>> p.add("test", 42)
>>> p
Parameters (default)
  .test = 42

>>> p.test
42
>>> p.test=43
>>> p.configs
['default']
>>> p.switch("another_config")
>>> p.add("test2", 10)
>>> p
Parameters (another_config)
  .test2 = 10
>>> p.switch("default")
>>> p
Parameters (default)
  .test = 43
>>>
```
