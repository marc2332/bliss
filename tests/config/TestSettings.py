# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.config import settings

def test_simple_setting(beacon):
    session = beacon.get("test_session")
    session.setup()

    myValue = "valval"
    sss = settings.SimpleSetting('mySkey', default_value=myValue)
    assert sss.get()=='valval'
    sss.set("V2")  # 'V2' key exists now in redis
    assert sss.get() == 'V2'

def test_hash_setting(beacon):
    session = beacon.get("test_session")
    session.setup()

    myDict = {"C1":"riri", "C2":"fifi"}
    shs = settings.HashSetting('myHkey', default_values=myDict)  # note the s :)
    assert myDict.items() == shs.items()
    assert myDict.values() == shs.values()
    assert shs.keys() == myDict.keys()

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
