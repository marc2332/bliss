# Beacon settings

## Settings

*Beacon settings* are helper classes to store data in the Redis database at
runtime from Python code, using BLISS.

Use cases for settings:

* on top of static configuration parameters
    - motor velocity, acceleration, limits
    - auto-gain on a Keithley

* to persistently keep (or share) information across executions (or
  across processes)
    - selected counter for plot
    - enabled loggers, log level
    - scan saving path, file template...


!!! danger "Direct access to the Redis database"
    `redis-cli` is a command-line tool to directly access to the Redis database.

    `redis-cli -s /tmp/redis.sock -n 0`

    WARNING: `redis-cli` must be use with care, alteration of the database integrity
    can lead to very strange behaviour.
    
    Never forget: *"With great power comes great responsibility"*


BLISS provides different classes for different kinds of settings.

## SimpleSetting

The `SimpleSetting` class is used to store a *scalar value*:

* int
* float
* string
* bool

Main usages are:

* to create the setting with a default value:

       `sss = SimpleSetting(<key>, default_value=<value>)`

* to set a value to store: `sss.set()`
* to read the stored value: `sss.get()`
* to reset the value to the default one: `sss.clear()`

### SimpleSetting Example

```python
from bliss.config import settings
magicNumber = 63825363
sss = settings.SimpleSetting('myIntkey', default_value=magicNumber)
print(sss)
# <SimpleSetting name=myIntkey value=None>
print(sss.get())
# 63825363    # this is the default value.
sss.set(42)

print(sss)
# <SimpleSetting name=myIntkey value=b'42'>

print(sss.get())
# 42

sss.clear()
print(sss.get())
# 63825363

sss.set(3.14)
```

`redis-cli` can be used to inspect the redis database:
```
% redis-cli -s /tmp/redis.sock -n 0
redis /tmp/redis.sock> keys my*
1) "myHkey"
2) "myIntkey"

redis /tmp/redis.sock> get myIntkey
"3.14"
```

After a restart of the session (or from another session):

```python
from bliss.config import settings
sss = settings.SimpleSetting('myIntkey')
print(sss.get())
# 3.14
```

After a `.clear()`, the key is removed from Redis database:

```python
sss.clear()
```

```
redis /tmp/redis.sock> keys myIntkey
(empty list or set)
```

### SimpleSetting behaviour

After instanciation (`sss = SimpleSetting('aKey', default_value=42)`), the
`SimpleSetting` object returns the `default_value`. This default value is NOT
saved in Redis database.

After a value has been set to the `SimpleSetting` object (`sss.set(3.14)`):

* this value is stored in the Redis database
* `SimpleSetting` object returns this value (`sss.get()`)

After a `clear()` (`sss.clear()`), the key is removed from Redis database and
the `SimpleSetting` object returns again the `default_value`.

!!! note

    `default_value` can be `None`, but a `SimpleSetting` cannot be set to `None`.


## BaseHashSetting and HashSetting

The `BaseHashSetting` class is used to represent a *dictionary* of
scalar values. `HashSetting` simply adds a kwarg `default_values` that
is a dictionary containing values taken as a fallback.

```python
from bliss.config import settings
myDict = {"key1":"value1", "key2":"value2"}
hs = settings.HashSetting('myHkey', default_values=myDict)
                                      # note the 's' in default_values
# 'hs' acts now as a dictionary.
print(hs["key1"])
# value1
print(hs["key2"])
# value2
hs["key1"]=3333
print(hs["key1"])
# 3333
```

Redis stores only key/value pairs that have changed:

```
% redis-cli -s /tmp/redis.sock -n 0
redis /tmp/redis.sock> hgetall myHkey
1) "key1"
2) "3333"
```

After a `.clear()`, the key is removed from Redis database.

A key can be added and removed:

bliss session:
```python
hs["newKey"]=45
```

redis:
```
hgetall myHkey
1) "key1"
2) "3333"
3) "newKey"
4) "45"
```

bliss session:
```python
hs.remove("newKey")
```

redis:
```
redis /tmp/redis.sock> hgetall myHkey
1) "key1"
2) "3333"
```


## QueueSetting

The `QueueSetting` class is used to represent a list of scalar values:

```python
>>> myList = ["a", "b", "c", "d"]
>>> sqs = settings.QueueSetting('myQkey')
>>> sqs.set(myList)
```

## ParametersWardrobe

`ParametersWardrobe` are more advanced objects -- it is used to group
simple settings, and to be able to switch from one set of values for
the parameters to another:

```python
>>> from bliss.config.settings import ParametersWardrobe
>>> p = ParametersWardrobe("my_params")
>>> p.add("test", 42)
>>> p
Parameters (default)
  .test = 42

>>> p.test
42
>>> p.test=43
>>> p.configs
['default']
>>> p.switch("another_config") - default
>>> p.add("test2", 10)
>>> p
Parameters (another_config) - default
  .test2 = 10
>>> p.switch("default")
>>> p
Parameters (default)
  .test = 43
>>>
```
