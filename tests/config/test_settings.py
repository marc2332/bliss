# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.config import settings
import cPickle

class DummyObject(object):
    pass

def test_simple_setting(beacon):
    session = beacon.get("test_session")
    session.setup()

    myValue = "valval"
    sss = settings.SimpleSetting('mySkey', default_value=myValue)
    assert sss.get()=='valval'
    sss.set("V2")  # 'V2' key exists now in redis
    assert sss.get() == 'V2'

def test_simple_setting_types(beacon):
    session = beacon.get("test_session")
    session.setup()

    # INT
    anIntValue = 666
    iii = settings.SimpleSetting('myIntkey', default_value=anIntValue)
    assert iii.get() == anIntValue
    iii.set(63825363)
    assert iii.get() == 63825363
    assert type(iii.get()) is int

    # FLOAT
    aFloatValue = 3.14159
    fff = settings.SimpleSetting('myFloatkey', default_value=aFloatValue)
    assert fff.get() == aFloatValue
    fff.set(2.71)
    assert fff.get() == pytest.approx(2.71, 0.001)
    assert type(fff.get()) is float

    # STRING
    aStringValue = "Hello World !"
    sss = settings.SimpleSetting('myStringKey', default_value=aStringValue)
    assert sss.get() == aStringValue
    sss.set("Good bye")
    assert sss.get() == "Good bye"
    assert type(sss.get()) is str

    # BOOLEAN
    aBoolValue = False
    bbb = settings.SimpleSetting('myBoolKey', default_value=aBoolValue)
    assert bbb.get() == aBoolValue
    bbb.set(True)
    assert bbb.get() == True
    assert type(bbb.get()) is bool

    # TUPLE
    aTupleValue = (1, 2, 3)
    ttt = settings.SimpleSetting('myTupleKey', default_value=aTupleValue)
    assert ttt.get() == aTupleValue
    ttt.set(('a', 'b', 'c'))
    # Oh oH !!! this is now a string.
    assert ttt.get() == "('a', 'b', 'c')"
    assert type(ttt.get()) is str

def test_hash_setting(beacon):
    session = beacon.get("test_session")
    session.setup()

    myDict = {"C1":"riri", "C2":"fifi"}
    shs = settings.HashSetting('myHkey', default_values=myDict)  # note the s :)
    assert myDict.items() == shs.items()
    assert myDict.values() == shs.values()
    assert shs.keys() == myDict.keys()

def test_hash_setting_default_value(beacon):
    shs = settings.HashSetting("myNewHkey")

    test_object = DummyObject()

    assert shs.get("a") is None
    setting_object = shs.get("a", default=test_object)
    assert test_object is setting_object

def test_hash_setting_default_value_readwrite_conv(beacon):
    shs = settings.HashSetting("myNewHkey",
                               read_type_conversion=settings.pickle_loads,
                              write_type_conversion=cPickle.dumps)

    test_object = DummyObject()

    assert shs.get("a") is None
    setting_object = shs.get("a", default=test_object)
    assert test_object is setting_object

def test_queue_setting(beacon):
    session = beacon.get("test_session")
    session.setup()

    myList = ["a", "b", "c", "d"]

    sqs = settings.QueueSetting('myQkey')
    sqs.set(myList)
    assert sqs.pop_back() == "d"
    # myList = ["a", "b", "c"]
    assert sqs.pop_front() == "a"
    # myList = ["b", "c"]
    sqs.remove("c")
    # myList = ["b"]
    assert sqs.pop_back() == "b"

    with pytest.raises(ValueError):
        print settings.InvalidValue()
