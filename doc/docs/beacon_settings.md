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

`ParametersWardrobe` is a more advanced object used to group
simple settings and to be able to switch from one set of values to another set easly.

We call the different sets with the name of `instances`.
Every instance has a `name` and share the same attributes with other instances.

You can imagine and visualize a ParameterWardrobe as a table where rows are the attributes and column are the instances. 
In fact **we can use the values from one column/instance at a time.**

The name of ParameterWardrobe comes from the idea of having some parts of the body to dress and some **suit of clothes** 
to choose from, for example: working suit, night suit, swimming suit.


Let's to an example with a `dress` object,
```py
BLISS [10]: dress = ParametersWardrobe('dress')  # this creates a Wardrobe with a 'default' instance
BLISS [11]: dress.current_istance
BLISS [11]: 'default'
BLISS [12]: dress.add('body','shirt')  # adding some slots default dressing
BLISS [13]: dress.add('head','nothing')
BLISS [14]: dress.add('feet','tennis shoes')
BLISS [15]: dress.add('legs','jeans')
BLISS [16]: dress
  Out [17]: Parameters (default) -

              .body           = 'shirt'
              .creation_date  = '2019-06-05-12:38'
              .feet           = 'tennis shoes'
              .head           = 'nothing'
              .last_accessed  = '2019-06-05-12:38'
              .legs           = 'jeans'
```
So you have your default suit of dress that you can use with dotted notation inside your code:

```py
BLISS [25]: dress.body
  Out [25]: 'shirt'

BLISS [26]: dress.body = "T shirt"
BLISS [27]: dress.body
  Out [27]: 'T shirt'
```

Values can be accessed and changed using dot notation.

At this point you would like to add another suit of clothes:

```py
BLISS [28]: dress.switch("Night dress")
BLISS [29]: dress
  Out [29]: Parameters (Night dress) - default

              .body           = 'T shirt'
              .creation_date  = '2019-06-05-14:30'
              .feet           = 'tennis shoes'
              .head           = 'nothing'
              .last_accessed  = '2019-06-05-14:30'
              .legs           = 'jeans'


BLISS [30]: dress.body = 'Jacket'
BLISS [31]: dress.feet = "Nice shoes"
BLISS [32]: dress.legs = "Black trousers"
BLISS [33]: dress
  Out [33]: Parameters (Night dress) - default

              .body           = 'Jacket'
              .creation_date  = '2019-06-05-14:30'
              .feet           = 'Nice shoes'
              .head           = 'nothing'
              .last_accessed  = '2019-06-05-14:30'
              .legs           = 'Black trousers'
```

Now we have two *instances* of dress and  we are currently using `Night dress`.

Whe can change values and visualize them. If no value is assigned to the instance
default is taken.

Let's add *another instance* and use a method to visualize all instances in a 
tabular form:

```python

BLISS [34]: dress.switch('swim')
BLISS [35]: dress.feet = "nothing"
BLISS [36]: dress.head = "swim glasses"
BLISS [37]: dress.body = "nothing"
BLISS [38]: dress.legs = "swimsuit"
BLISS [39]: dress.instances
  Out [39]: ['swim', 'Night dress', 'default']
BLISS [40]: dress.show_table()
* asterisks means value not stored in database (default is taken)
# hash means a computed attribute (property)


                  swim (SELECTED)         Night dress             default
-------------  ------------------  ------------------  ------------------
         body             nothing              Jacket             T shirt
creation_date  # 2019-06-05-14:37  # 2019-06-05-14:30  # 2019-06-05-12:38
         feet             nothing          Nice shoes        tennis shoes
         head        swim glasses           * nothing             nothing
last_accessed  # 2019-06-05-14:37  # 2019-06-05-14:30  # 2019-06-05-12:38
         legs            swimsuit      Black trousers               jeans
```

With `.show_table()` we have a complete vision of what is contained in all `instances`.

ParametersWardrobe can handle all basic types of data like:

 * string
 * bool
 * list (including numpy array)
 * tuple
 * dict
 * set

Let's do another example:

```python
BLISS [40]: all = ParametersWardrobe('all')
BLISS [41]: all.add('bool',True)
BLISS [42]: all.add('dict', {'index':'value'})
BLISS [43]: all.add('list')  # without passing a default value (will be None)
BLISS [44]: all.list = [1,2,3]  # assigning a value later
BLISS [45]: import numpy
BLISS [46]: numpy.ndarray((1,2,3))
  Out [46]: array([[[ 6.91528554e-310,  4.64581452e-310,  5.86245261e-160],
                    [ 6.91528554e-310,  4.64581452e-310, -1.39151878e+147]]])

BLISS [47]: all.list = numpy.ndarray((1,2,3))
BLISS [48]: all.list
  Out [48]: array([[[6.91528554e-310, 4.64581452e-310, 5.86245261e-160],
                    [6.91528554e-310, 4.64581452e-310, 1.39151878e+147]]])

BLISS [49]: all
  Out [49]: Parameters (default) - 
            
              .bool           = True
              .creation_date  = '2019-06-05-14:43'
              .dict           = {'index': 'value'}
              .last_accessed  = '2019-06-05-14:43'
              .list           = array([[[6.91528554e-310, 4.64581452e-310, 5.86245261e-160],
                    [6.91528554e-310, 4.64581452e-310, 1.39151878e+147]]])
```

### Useful methods of ParameterWardrobe are:

Here is given a list of methods and purposes of ParameterWardrobe. To understand
the details of usage just read the docstring with python `help(...)` method from Bliss shell.

####  .add 
To add a new attribute to the Wardrobe

####  .switch
To switch current instance to another one and creating a new one if does not exist.

####  .remove
Allows deleting instances or attributes

####  .freeze
Freezes the current instance hardwriting values that are taken from default.

####  .to_dict and .from_dict
Allows to easily import/export instances, the main purpose is to have data in a form that
can be used inside shell or scripts to do computation.


####  .to_file and .from_file
Saves and imports data using yml format to and from a file.
The purpose is to `dump` instances and keep a copy for backup reasons.
Not created for manipulation purposes.
Keep in mind that exporting to file in fact `freezes` the data in the file,
This means that if you are using an instance that takes some values from
*'default'* instance the act of writing to the file will hardcode these values
to file.
You should be aware that an `instance` imported from_file will have her
own values for every attribute and will not use default ones.

####  .to_beacon and .from_beacon
The same purpose and behaviour than *to_file* and *from_file*, but the files
are saved in Beacon on a subfolder called **wardrobe** as **.dat** files.

####  .instances
Gives the list of all instance names.

####  .creation_date and .last_accessed
Read only values (properties) that gives some information for ParameterWardrobe
mainteinance.
