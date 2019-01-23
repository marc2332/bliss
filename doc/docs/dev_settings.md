bliss-settings-how-to:

# Bliss settings how to

This chapter explains:

* how to use BLISS *settings* (`SimpleSetting`, `HashSetting` and `QueueSetting`)
* how to inspect key-value database so see how and what is saved in REDIS database


## What are BLISS settings ?

A setting is a *value*, *list* or *dictionary* that has to be kept in
memory and to be restoreed after a shutdown of your session or
program.

Settings are saved in the *REDIS key-value database*. Scalar values
are saved as *strings* but `settings` class transtypes them.


## Settings Classes

Various types of setting can be used in a BLISS project.

### SimpleSetting


The `SimpleSetting` class is used to keep in memory a *scalar value*.
Python base-type (except tuples) are usable as value:

* int
* float
* string
* bool
* tuple : NO

Example:

    from bliss.config import settings
    magicNumber = 63825363
    iii = settings.SimpleSetting('myIntkey', default_value=magicNumber)
    assert iii.get() == magicNumber
    iii.set(42)
    assert iii.get() == 42
    assert type(iii.get()) is int

The `default_value` is returned by the `SimpleSetting` object until it has been set.
Once the object has been set, the value is saved in redis database in order to be retrieved
after a shutdown of a BLISS session.


### HashSetting


The `HashSetting` class is used to represent a dictionary of scalar values:

    myDict = {"C1":"riri", "C2":"fifi"}
    shs = settings.HashSetting('myHkey', default_values=myDict)  # note the s :)


### QueueSetting


The `QueueSetting` class is used to represent a list of scalar values:

    myList = ["a", "b", "c", "d"]
    sqs = settings.QueueSetting('myQkey')
    sqs.set(myList)


## To check REDIS' entrails : `redis-cli`


`redis-cli` command line tool can be used to inspect what is saved by
the redis database.

(CLI stands for Command Line Interface)

To know if a key is present:

    (bliss) pcsht:~/PROJECTS/bliss % redis-cli
    127.0.0.1:6379> keys myIntkey
    1) "myIntkey"

or not:

  127.0.0.1:6379> keys licorne
  (empty list or set)

A joker character to get all keys or a specified sub-set can also be
used:

    127.0.0.1:6379> keys *
     1) "myFloatkey"
     2) "align_counters:default"
         ...
    12) "myQkey"
    13) "axis.simot1"

    127.0.0.1:6379> keys a*
     1) "axis.pzth"
     2) "align_counters:default"
     3) "align_counters:align"
     4) "axis.simot1"
     5) "align_counters"

Values attached to a key can be read:

For a scalar value:

    127.0.0.1:6379> get myIntkey
     "42"

For a dictionary vlaue:

    127.0.0.1:6379> hgetall axis.pzth
     1) "velocity"
     2) "11.0000002"
     3) "offset"
     4) "0"
     5) "acceleration"
     6) "1.0"

For a list value:

    127.0.0.1:6379> LRANGE myQkey 0 -1
     1) "a"
     2) "b"
     3) "c"
     4) "d"


## Correspondence between REDIS and BLISS

Example of imbrication of BLISS and REDIS:

                        BLISS                                           REDIS
  
    [80]: from bliss.config.settings import SimpleSetting
    [81]: fff = SimpleSetting('fkey', default_value=321)
    [82]: fff.get()
     out: 321
                                                            127.0.0.1:6379> keys fkey
                                                            (empty list or set)
                                                            127.0.0.1:6379>  get fkey
                                                            (nil)
    [83]: fff.set(987)
                                                            127.0.0.1:6379> keys fkey
                                                            1) "fkey"
    [84]: fff.get()
     out: 987
                                                            127.0.0.1:6379> get fkey
                                                            "987"

A value can be set and a key deleted from `redis-cli`:

                       BLISS                                             REDIS
 
                                                            127.0.0.1:6379> set fkey 123
                                                            OK
    [85]: fff.get()
     out: 123
                                                            127.0.0.1:6379> get fkey
                                                            "123"
                                                            127.0.0.1:6379> del fkey
                                                            (integer) 1
                                                            127.0.0.1:6379> get fkey
                                                            (nil)
 
    [86]: fff.get()
     out: 321    # default_value is returned


