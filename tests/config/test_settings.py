# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.config import settings
import pickle
from bliss.common.axis import Axis
import datetime


class DummyObject(object):
    pass


def test_simple_setting(session):
    myValue = "valval"
    sss = settings.SimpleSetting("mySkey", default_value=myValue)
    assert sss.get() == "valval"
    sss.set("V2")  # 'V2' key exists now in redis
    assert sss.get() == "V2"


def test_simple_setting_types(session):
    # INT
    anIntValue = 666
    iii = settings.SimpleSetting("myIntkey", default_value=anIntValue)
    assert iii.get() == anIntValue
    iii.set(63825363)
    assert iii.get() == 63825363
    assert type(iii.get()) is int

    # FLOAT
    aFloatValue = 3.14159
    fff = settings.SimpleSetting("myFloatkey", default_value=aFloatValue)
    assert fff.get() == aFloatValue
    fff.set(2.71)
    assert fff.get() == pytest.approx(2.71, 0.001)
    assert type(fff.get()) is float

    # STRING
    aStringValue = "Hello World !"
    sss = settings.SimpleSetting("myStringKey", default_value=aStringValue)
    assert sss.get() == aStringValue
    sss.set("Good bye")
    assert sss.get() == "Good bye"
    assert type(sss.get()) is str

    # BOOLEAN
    aBoolValue = False
    bbb = settings.SimpleSetting("myBoolKey", default_value=aBoolValue)
    assert bbb.get() == aBoolValue
    bbb.set(True)
    assert bbb.get() == True
    assert type(bbb.get()) is bool

    # TUPLE
    aTupleValue = (1, 2, 3)
    ttt = settings.SimpleSetting("myTupleKey", default_value=aTupleValue)
    assert ttt.get() == aTupleValue
    ttt.set(("a", "b", "c"))
    # Oh oH !!! this is now a string.
    assert ttt.get() == "('a', 'b', 'c')"
    assert type(ttt.get()) is str


def test_basehash_setting(session):
    my_dict = {"C1": "riri", "C2": "fifi"}
    shs = settings.BaseHashSetting("newkey")  # note the s :)
    for k, v in my_dict.items():
        shs[k] = v

    assert list(my_dict.items()) == list(shs.items())
    assert list(my_dict.values()) == list(shs.values())
    assert list(my_dict.keys()) == list(shs.keys())


def test_hash_setting(session):
    myDict = {"C1": "riri", "C2": "fifi"}
    shs = settings.HashSetting("myHkey", default_values=myDict)  # note the s :)
    assert list(myDict.items()) == list(shs.items())
    assert list(myDict.values()) == list(shs.values())
    assert list(shs.keys()) == list(myDict.keys())


def test_hash_setting_default_value(beacon):
    shs = settings.HashSetting("myNewHkey")

    test_object = DummyObject()

    assert shs.get("a") is None
    setting_object = shs.get("a", default=test_object)
    assert test_object is setting_object


def test_hash_setting_default_value_readwrite_conv(beacon):
    shs = settings.HashSetting(
        "myNewHkey",
        read_type_conversion=settings.pickle_loads,
        write_type_conversion=pickle.dumps,
    )

    test_object = DummyObject()

    assert shs.get("a") is None
    setting_object = shs.get("a", default=test_object)
    assert test_object is setting_object


def test_queue_setting(session):
    myList = ["a", "b", "c", "d"]

    sqs = settings.QueueSetting("myQkey")
    sqs.set(myList)
    assert sqs.pop_back() == "d"
    # myList = ["a", "b", "c"]
    assert sqs.pop_front() == "a"
    # myList = ["b", "c"]
    sqs.remove("c")
    # myList = ["b"]
    assert sqs.pop_back() == "b"

    with pytest.raises(ValueError):
        print(settings.InvalidValue())


def test_pipeline_settings(beacon):
    t = settings.HashSetting("super_fancy")
    values = [("val1", 1), ("val2", 2)]
    with settings.pipeline(t):
        for val_name, value in values:
            t[val_name] = value
    try:
        with settings.pipeline(t) as p:
            for val_name, value in values:
                t[val_name]  # get
            assert p.execute() == [b"1", b"2"]
    finally:
        t.clear()


def test_pipeline_bad_setting_object(beacon):
    class BadSetting:
        pass

    bad_setting = BadSetting()
    with pytest.raises(TypeError):
        with settings.pipeline(bad_setting):
            pass


def test_parameter_wardrobe_1(session):
    spw = settings.ParametersWardrobe("myPWkey")
    # checking default is created
    assert "default" in spw.configs
    assert len(spw.configs) == 1

    numbers = (("first", 1), ("second", 2), ("third", 3))
    romans_numbers = (("first", "I"), ("second", "II"), ("third", "III"))

    for k, v in numbers:
        spw.add(k, v)  # adding parameters
        assert hasattr(spw, k)  # check existance
        assert getattr(spw, k) == v  # check values
        assert isinstance(getattr(spw, k), int)  # check types

    # creating a new set of parameters
    spw.switch("roman")
    for k, v in numbers:
        assert getattr(spw, k) == v  # check values
        assert isinstance(getattr(spw, k), int)  # check types
    # assigning new values to romans
    for k, v in romans_numbers:
        setattr(spw, k, v)
    for k, v in romans_numbers:
        assert getattr(spw, k) == v  # check values
        assert isinstance(getattr(spw, k), str)  # check types
    # switch back to default
    spw.switch("default")
    for k, v in numbers:
        assert getattr(spw, k) == v  # check values
        assert isinstance(getattr(spw, k), int)  # check types
    # deleting
    spw.remove("roman")
    assert "roman" not in spw.configs
    assert "default" in spw.configs


def test_parameters_wardrobe_switch(session):
    dress = settings.ParametersWardrobe("dress")
    slots = ("head", "body", "legs")
    default = ("nothing", "t-shirt", "jeans")

    # creating default
    for k, v in zip(slots, default):
        dress.add(k, v)

    check = dress.to_dict()
    for k, v in zip(slots, default):
        assert check[k] == v
    len(check) == 7

    dress.switch("casual")  # on casual
    dress.head = "football hat"
    dress.switch("default")  # on default
    assert dress.head == "nothing"
    dress.switch("casual")  # on casual
    assert dress.head == "football hat"
    dress.switch("night")  # on night
    dress.body = "shirt"
    dress.remove(".legs")
    with pytest.raises(KeyError):
        dress.legs

    check = dress.to_dict()
    assert check.get("head") == "nothing"
    assert check.get("body") == "shirt"
    assert check.get("_creation_date") is not None
    assert isinstance(check.get("_last_accessed"), str)
    assert len(check) == 6

    # testing configs method
    for suite in ("a", "b", "c"):
        with pytest.raises(AssertionError):
            assert suite in dress.configs
    for suite in ("casual", "default", "night"):
        assert suite in dress.configs


def test_parameter_wardrobe_init_with_default(session):
    def_val = {"pasta": 80, "pizza": 150, "cheese": "1 piece", "meat": "1 steak"}
    food = settings.ParametersWardrobe("food_per_person", default_values=def_val)
    assert food.pasta == 80
    assert food.pizza == 150
    assert food.cheese == "1 piece"
    assert food.meat == "1 steak"
    with pytest.raises(AttributeError):
        food.other == "boh"
    food.switch("double")
    assert food.pasta == 80
    assert food.pizza == 150
    assert food.cheese == "1 piece"
    assert food.meat == "1 steak"
    with pytest.raises(AttributeError):
        food.other == "boh"
    food.pasta = 150
    assert food.pasta == 150
    food.switch("default")
    assert food.pasta == 80


def test_parameter_wardrobe_from_dict(session):
    def_val = {"pasta": 80, "pizza": 150, "cheese": "1 piece", "meat": "1 steak"}
    food = settings.ParametersWardrobe("otherfood")
    for k in def_val.keys():
        # creating default None values
        food.add(k)
    food.switch("junk")
    food.from_dict(def_val)
    assert food.pasta == 80
    assert food.pizza == 150
    assert food.cheese == "1 piece"
    assert food.meat == "1 steak"
    with pytest.raises(AttributeError):
        food.other == "boh"
    food.switch("double")
    for k in def_val.keys():
        # all default are None
        assert getattr(food, k) == None
    with pytest.raises(AttributeError):
        food.from_dict({"wrong": 1, "parameters": 2})


def test_parameter_wardrobe_none(session):
    sport = settings.ParametersWardrobe("sport")
    sport.add("Soccer")
    # check if is creating Soccer and if is assigning None
    assert sport.Soccer == None


def test_parameter_wardrobe_global_object(session):
    # checks if we are able to store references to
    # global objects
    motors = settings.ParametersWardrobe("motors")
    m0 = session.config.get("m0")
    motors.add("m0", m0)  # creating reference to motor m0
    del motors
    check_motors = settings.ParametersWardrobe("motors")
    # checking if reference is ok
    assert isinstance(check_motors.m0, Axis)


def test_wardrobe_remove(session):
    dont_change_me = settings.ParametersWardrobe("notme", not_removable=["myself"])
    dont_change_me.add("myself", "best")
    dont_change_me.add("yourself", "how?")

    with pytest.raises(AttributeError):
        dont_change_me.remove(".myself")
    with pytest.raises(NameError):
        dont_change_me.remove("default")
    with pytest.raises(NameError):
        dont_change_me.remove("not existent name")
    assert dont_change_me.yourself == "how?"
    dont_change_me.remove(".yourself")
    with pytest.raises(KeyError):
        assert dont_change_me.yourself


def test_wardrobe_show_table(session, capsys):
    dress = settings.ParametersWardrobe("mydress")
    dress.add("_hideme")
    dress.add("showme")
    dress.show_table()
    captured = capsys.readouterr()
    # check hiding parameters with _
    assert "_hideme" not in captured.out
    assert "showme" in captured.out
    dress.add("hat", "football")
    dress.add("feet", "shoes")
    # check if asterisk is present
    dress.switch("sport")
    dress.feet = "tennis"
    dress.show_table()
    captured = capsys.readouterr()
    assert "* football" in captured.out
    assert "* tennis" not in captured.out
    assert "tennis" in captured.out


def test_wardrobe_get_current_config(session):
    games = settings.ParametersWardrobe("games")
    for name in "soccer tennis football squash".split():
        # create and switch to different sets
        games.switch(name)
        assert games.current_config == name
    for name in "soccer tennis football squash".split():
        # just switch to different created sets
        games.switch(name)
        assert games.current_config == name


def test_creation_time(session):
    drinks = settings.ParametersWardrobe("drinks")
    assert "wine" not in drinks.configs
    drinks.switch("wine")
    # get current time
    now = datetime.datetime.now()
    # convert string to datetime obj
    creation_date = datetime.datetime.strptime(drinks.creation_date, "%Y-%m-%d-%H:%M")
    assert abs(now - creation_date) < datetime.timedelta(seconds=60)
    last_accessed = datetime.datetime.strptime(drinks.creation_date, "%Y-%m-%d-%H:%M")
    assert abs(now - last_accessed) < datetime.timedelta(seconds=60)

    # an empty Wardrobe has only creation/access info
    food = settings.ParametersWardrobe("food")
    assert len(food.to_dict()) == 4
    creation_time = "2018-07-22-07:00"

    food._creation_date = creation_time
    food._last_accessed = creation_time

    food.switch("first")
    food.switch("default")
    assert food.creation_date == creation_time
    assert food.last_accessed != creation_time


def test_from_dict_ok(session):
    colors = settings.ParametersWardrobe("colors")
    colors.add("background", "black")
    colors.add("foreground", "white")
    colors.switch("portrait")
    new_colors = {"background": "yellow", "foreground": "blue"}

    colors.from_dict(new_colors)
    assert colors.background == "yellow"
    assert colors.foreground == "blue"

    colors.switch("default")

    assert colors.background == "black"
    assert colors.foreground == "white"

    with pytest.raises(AttributeError):
        # attribute does not exist in Wardrobe
        colors.from_dict({**new_colors, **{"border": "pink"}})


def test_from_dict_not_ok(session):
    cats = settings.ParametersWardrobe("cats")
    with pytest.raises(AttributeError):
        cats.from_dict({"breed": "snowcat"})
    with pytest.raises(TypeError):
        cats.from_dict({})
    with pytest.raises(TypeError):
        cats.from_dict(None)
    with pytest.raises(TypeError):
        cats.from_dict()


class MyPar(settings.ParametersWardrobe):
    """
    Test class to check property attributes
    """

    SLOTS = []

    def __init__(self, name):
        super().__init__(name, property_attributes=["myproperty"])

    @property
    def myproperty(self):
        return "OK"


def test_from_and_to_dict_with_inheritance(session):
    mypar = MyPar("mypar")
    mypar.add("first", "I")
    mypar.add("second", "I(")
    assert mypar.myproperty == "OK"
    dict_ = mypar.to_dict()
    assert len(dict_) == 7
    mypar.from_dict(dict_)
    with pytest.raises(AttributeError):
        mypar.from_dict({**dict_, **{"fakeattr": 123}})
    with pytest.raises(AttributeError):
        # can't set attribute
        mypar.myproperty = 23


def test_creation_and_update_appear_on_shell(session, capsys):
    fake = settings.ParametersWardrobe("fake")
    print(fake)
    captured = capsys.readouterr()
    assert "last_accessed" in captured.out
    assert "creation_date" in captured.out
    fake.show_table()
    captured = capsys.readouterr()
    assert "last_accessed" in captured.out
    assert "creation_date" in captured.out


def test_non_removable(session):
    fake = settings.ParametersWardrobe("fake", not_removable=("immortal",))
    with pytest.raises(AttributeError):
        fake.immortal  # not yet created
    fake.add("immortal", "me")
    with pytest.raises(AttributeError):
        fake.remove(".immortal")
