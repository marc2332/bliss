# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import datetime
import os
import pickle
import gevent

import pytest

from bliss.config import settings
from bliss.common.axis import Axis
from bliss.config.conductor.client import get_default_connection


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


def test_basehash_settings_ttl(session):
    ihavetodie = settings.BaseHashSetting("ihavetodie")
    ihavetodie["I"] = "alive"
    assert ihavetodie.ttl(1)
    assert ihavetodie["I"] == "alive"
    gevent.sleep(1.5)
    with pytest.raises(KeyError):
        ihavetodie["I"]


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


"""
def test_hash_settings_from_keys(beacon):
    fromk = settings.OrderedHashSetting("fromk")
    fromk.set({"first":"I","second":"II"})
    assert list(fromk.fromkeys('first','second','third')) == ['I',"II",None]
    assert list(fromk.fromkeys('third','second','first')) == [None, 'II',"I"]

    generator = fromk.fromkeys('first','second','third')
    assert next(generator) =="I"
    assert next(generator) =="II"
    fromk['third'] = "III"
    assert next(generator) == None
"""


def test_orderedhash_settings(beacon):
    data = tuple(
        (str(n), v) for n, v in enumerate((ch for ch in "abcdefghilmnopqrstuvz"))
    )
    ohs = settings.OrderedHashSetting("ordhashset")
    for k, v in data:
        ohs[k] = v

    get_all = ohs.get_all()

    assert tuple(ohs.items()) == data == tuple(get_all.items())
    assert tuple(ohs.keys()) == tuple(k for k, v in data)


def test_orderedhash_settings_remove(beacon):
    removeme = settings.OrderedHashSetting("removeme")
    removeme["a"] = "a"
    removeme["b"] = "b"
    removeme["c"] = (1, 2, 3)
    assert tuple(removeme.items()) == (("a", "a"), ("b", "b"), ("c", "(1, 2, 3)"))
    assert tuple(removeme.values()) == ("a", "b", "(1, 2, 3)")
    removeme.remove("b")
    assert not removeme.has_key("b")
    assert tuple(removeme.items()) == (("a", "a"), ("c", "(1, 2, 3)"))


def test_orderedhash_settings_update(beacon):
    updateme = settings.OrderedHashSetting("updateme")
    updateme.update({1: 1, 2: 2})
    assert tuple(updateme) == (("1", "1"), ("2", "2"))
    updateme.update({4: 4, 3: 3})
    assert tuple(updateme) == (("1", "1"), ("2", "2"), ("4", "4"), ("3", "3"))


def test_orderedhash_settings_update(beacon):
    updateme = settings.OrderedHashSetting("updateme")
    updateme["a"] = 1
    updateme["b"] = 2
    updateme.update({"c": 3})

    assert tuple(updateme.keys()) == tuple(("a", "b", "c"))
    assert len(updateme) == 3
    assert tuple(updateme.values()) == tuple((1, 2, 3))


def test_orderedhash_settings_set(beacon):
    setme = settings.OrderedHashSetting("setme")
    setme.set({"first": "I", "second": "II"})

    assert tuple((k, v) for k, v in setme.get_all().items()) == tuple(
        (("first", "I"), ("second", "II"))
    )
    setme.set({"firstagain": 1, "secondagain": 2})
    assert tuple((k, v) for k, v in setme.get_all().items()) == tuple(
        (("firstagain", 1), ("secondagain", 2))
    )
    setme.set({"1": 11, "2": 22})
    assert tuple((k, v) for k, v in setme.get_all().items()) == tuple(
        (("1", 11), ("2", 22))
    )
    assert len(setme) == 2
    del setme["1"]
    assert len(setme) == 1


def test_orderedhash_settings_has_key(beacon):
    haskeys = settings.OrderedHashSetting("haskeys")
    haskeys.set({"first": "I", "second": "II"})
    for item in "first", "second":
        assert haskeys.has_key(item)


"""
def test_orderedhash_settings_from_keys(beacon):
    fromkeys = settings.OrderedHashSetting("fromkeys")
    fromkeys.set({"first":"I","second":"II"})
    assert list(fromkeys.fromkeys('first','second','third')) == ['I',"II",None]
    assert list(fromkeys.fromkeys('third','second','first')) == [None, 'II',"I"]
"""


def test_orderedhash_settings_ttl(session):
    ihavetodie = settings.OrderedHashSetting("ihavetodie")
    ihavetodie["I"] = "alive"
    assert ihavetodie.ttl(1)
    assert ihavetodie["I"] == "alive"
    gevent.sleep(1.5)
    with pytest.raises(KeyError):
        ihavetodie["I"]
    assert len(ihavetodie._cnx().zrange(ihavetodie._name_order, 0, -1)) == 0


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
    assert "default" in spw.instances
    assert len(spw.instances) == 1

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
    assert "roman" not in spw.instances
    assert "default" in spw.instances


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

    check = dress.to_dict(export_properties=True)
    assert check.get("head") == "nothing"
    assert check.get("body") == "shirt"
    assert check.get("_creation_date") is not None
    assert isinstance(check.get("_last_accessed"), str)
    assert len(check) == 6
    check = dress.to_dict()
    assert len(check) == 2

    # testing instances method
    for suite in ("a", "b", "c"):
        with pytest.raises(AssertionError):
            assert suite in dress.instances
    for suite in ("casual", "default", "night"):
        assert suite in dress.instances


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
    motors = settings.ParametersWardrobe("motors_chk")
    m0 = session.config.get("m0")
    motors.add("m0", m0)  # creating reference to motor m0
    del motors
    check_motors = settings.ParametersWardrobe("motors_chk")
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


def test_wardrobe_get_current_instance(session):
    games = settings.ParametersWardrobe("games")
    for name in "soccer tennis football squash".split():
        # create and switch to different sets
        games.switch(name)
        assert games.current_instance == name
    for name in "soccer tennis football squash".split():
        # just switch to different created sets
        games.switch(name)
        assert games.current_instance == name


def test_creation_time(session):
    drinks = settings.ParametersWardrobe("drinks")
    assert "wine" not in drinks.instances
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
    assert len(food.to_dict(export_properties=True)) == 4
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
    assert "myproperty" not in dict_  # check presence of property
    dict_ = mypar.to_dict(export_properties=True)
    assert "myproperty" in dict_  # check presence of property

    assert len(dict_) == 7
    mypar.from_dict(dict_)
    with pytest.raises(AttributeError):
        mypar.from_dict({**dict_, **{"fakeattr": 123}})
    with pytest.raises(AttributeError):
        # can't set attribute
        mypar.myproperty = 23
    with pytest.raises(NameError):
        mypar.add("myproperty", 123)


def test_creation_and_update_appear_on_shell(session, capsys):
    fake = settings.ParametersWardrobe("fake")
    print(fake.__info__())
    captured = capsys.readouterr()
    assert "last_accessed" in captured.out
    assert "creation_date" in captured.out
    fake.show_table()
    captured = capsys.readouterr()
    assert "last_accessed" in captured.out
    assert "creation_date" in captured.out


def test_dir_shows_attrs_on_shell(session, capsys):
    myfake = MyPar("myfake")
    myfake.add("band", "rolling stones")
    myfake.add("music", ["rock", "pop"])
    print(dir(myfake))
    captured = capsys.readouterr()
    for (
        name
    ) in "add remove switch instance current_instance to_dict from_dict from_file freeze show_table creation_date last_accessed band music myproperty".split():
        assert name in captured.out


"""
def test_delete_wardrobe(session):
    deleting = settings.ParametersWardrobe('deleting')
    deleting.add('erasing',1000)
    assert deleting.erasing == 1000
    del deleting
    deleting = settings.ParametersWardrobe('deleting')
    with pytest.raises(AttributeError):
        deleting.erasing
        """


def test_non_removable(session):
    fake = settings.ParametersWardrobe("fake", not_removable=("immortal",))
    with pytest.raises(AttributeError):
        fake.immortal  # not yet created
    fake.add("immortal", "me")
    with pytest.raises(AttributeError):
        fake.remove(".immortal")


def test_bad_name_for_attribute(session):
    bad = settings.ParametersWardrobe("bad")
    for name in r"!@#$%^&*()123804/`-+=,./".split():
        with pytest.raises(TypeError):
            bad.add(name)


@pytest.fixture
def materials(session, beacon):
    ma = settings.ParametersWardrobe("materials")
    ma.add("color")
    ma.add("specific_weight")
    ma.add("dimensions")
    ma.add("pieces")
    ma.add("precious", False)
    ma.add("motor", session.config.get("roby"))

    ma.switch("water")
    ma.color = "transparent"
    ma.specific_weight = 1

    ma.switch("gold")
    ma.color = "gold"
    ma.specific_weight = 19.32
    ma.dimensions = (1, 2, 3)
    ma.pieces = {"first": 10.3, "second": 20.2, "count": [5, 2, 5]}
    ma.precious = True

    ma.switch("copper")
    ma.color = "yellow-brown"
    ma.specific_weight = 8.96
    ma.dimensions = (5, 10, 15)
    ma.pieces = {"first": 40.3, "second": 27.2, "count": [1, 2, 3]}
    ma.motor = session.config.get("robz")

    yield ma


def test_wardrobe_to_yml_file(session, materials):

    path = "/tmp/materials_copper.yml"
    path_1 = "/tmp/materials_copper_1.yml"

    # delete files if they exists
    if os.path.isfile(path):
        os.remove(path)
    if os.path.isfile(path_1):
        os.remove(path_1)

    materials.switch("copper")

    # export only copper (current instance)
    materials.to_file(path)

    materials.switch("gold")
    materials.to_file(path_1, "copper")
    with open(path) as f, open(path_1) as f1:
        # those approach are equivalent
        assert f.read() == f1.read()

    # export all materials
    materials.to_file("/tmp/materials_all.yml", *materials.instances)


def test_wardrobe_from_yml_file(session):
    copper_reload = settings.ParametersWardrobe("materials_reload")

    # setting default values
    copper_reload.add("color", "nocolor")
    copper_reload.add("specific_weight", 0)
    copper_reload.add("dimensions")
    copper_reload.add("pieces")
    copper_reload.add("precious")
    copper_reload.add("motor")

    copper_reload.from_file("/tmp/materials_copper.yml", instance_name="copper")
    assert copper_reload.color == "yellow-brown"
    assert copper_reload.specific_weight == 8.96
    assert copper_reload.dimensions == (5, 10, 15)
    assert copper_reload.pieces == {"first": 40.3, "second": 27.2, "count": [1, 2, 3]}
    assert copper_reload.precious == False
    assert copper_reload.motor == session.config.get("robz")

    materials_reload = settings.ParametersWardrobe("materials_reload")
    materials_reload.add("color", "nocolor")
    materials_reload.add("specific_weight", 0)
    materials_reload.add("dimensions")
    materials_reload.add("pieces")
    materials_reload.add("precious")
    materials_reload.add("motor")

    materials_reload.switch("copper")
    materials_reload.from_file("/tmp/materials_all.yml", instance_name="copper")
    materials_reload.switch("gold")
    materials_reload.from_file("/tmp/materials_all.yml", instance_name="gold")
    materials_reload.switch("default")
    materials_reload.from_file("/tmp/materials_all.yml", instance_name="default")

    materials_reload.switch("gold")
    assert materials_reload.color == "gold"
    assert materials_reload.specific_weight == 19.32
    assert materials_reload.dimensions == (1, 2, 3)
    assert materials_reload.pieces == {
        "first": 10.3,
        "second": 20.2,
        "count": [5, 2, 5],
    }
    assert materials_reload.precious == True
    assert materials_reload.motor.name == session.config.get("roby").name

    materials_reload.switch("copper")
    assert materials_reload.color == "yellow-brown"
    assert materials_reload.specific_weight == 8.96
    assert materials_reload.dimensions == (5, 10, 15)
    assert materials_reload.pieces == {
        "first": 40.3,
        "second": 27.2,
        "count": [1, 2, 3],
    }
    assert materials_reload.precious == False
    assert materials_reload.motor.name == session.config.get("robz").name

    materials_reload.switch("default")
    # default should be loaded from file and be different
    # from previous values
    assert materials_reload.color == None
    assert materials_reload.specific_weight == None
    assert materials_reload.dimensions == None
    assert materials_reload.specific_weight == None
    assert materials_reload.precious == False
    assert materials_reload.motor.name == session.config.get("roby").name


def test_wardrobe_empty_from_yml_file(session):
    empty_material = settings.ParametersWardrobe("empty_material")
    with pytest.raises(KeyError):
        # current set is empty and to be strict we should not be able
        # to load values
        empty_material.from_file("/tmp/materials_all.yml")


def test_wardrobe_from_yml_file_partial(session):
    material = settings.ParametersWardrobe("material")
    material.add("color")
    material.add("specific_weight")
    material.add("other")  # this is not in the yml file but importing should work
    material.add("dimensions")
    material.add("pieces")
    material.add("precious")
    material.add("motor")
    # this should succeed
    material.from_file("/tmp/materials_all.yml", instance_name="copper")
    material.from_file("/tmp/materials_all.yml", instance_name="gold")
    material.from_file("/tmp/materials_all.yml", instance_name="default")


def test_wardrobe_check_atomic_operation(session):
    atomic = settings.ParametersWardrobe("atomic")
    atomic.add("first", 1)
    atomic.add("second", 2)
    d = atomic.to_dict()
    d["first"] = "I"
    d["second"] = "II"
    d["third"] = 3
    with pytest.raises(AttributeError):
        atomic.from_dict(d)
    assert atomic.first == 1
    assert atomic.second == 2
    with pytest.raises(AttributeError):
        atomic.third


def test_wardrobe_freeze(session):
    temperature = settings.ParametersWardrobe("temperature")
    temperature.add("water", "liquid")
    temperature.switch("t20")

    assert "water" not in temperature._get_redis_single_instance("t20")  # not in redis
    temperature.freeze()
    temperature.switch("warm", copy="default")
    assert "water" in temperature._get_redis_single_instance(
        "t20"
    )  # should be in Redis
    assert "water" in temperature._get_redis_single_instance(
        "warm"
    )  # should be in Redis


def test_wardrobe_low_level_methods(materials):
    assert materials._get_redis_single_instance("not existant") == {}
    with pytest.raises(NameError):
        assert materials._get_instance("not existant") == {}


def test_to_beacon(materials):
    materials.to_beacon("mat_eri-als23", *materials.instances)


def test_from_beacon(session):
    beacon_material = settings.ParametersWardrobe("beacon_material")
    beacon_material.add("color")
    beacon_material.add("specific_weight")
    beacon_material.add("dimensions")
    beacon_material.add("pieces")
    beacon_material.add("precious")
    beacon_material.add("motor")

    beacon_material.from_beacon("mat_eri-als23", "default")

    beacon_material.switch("copper")
    beacon_material.from_beacon("mat_eri-als23", "copper")

    beacon_material.switch("gold")
    beacon_material.from_beacon("mat_eri-als23", "gold")

    assert beacon_material.color == "gold"
    assert beacon_material.specific_weight == 19.32
    assert beacon_material.dimensions == (1, 2, 3)
    assert beacon_material.pieces == {"first": 10.3, "second": 20.2, "count": [5, 2, 5]}
    assert beacon_material.precious == True
    assert beacon_material.motor.name == session.config.get("roby").name

    beacon_material.switch("copper")
    assert beacon_material.color == "yellow-brown"
    assert beacon_material.specific_weight == 8.96
    assert beacon_material.dimensions == (5, 10, 15)
    assert beacon_material.pieces == {"first": 40.3, "second": 27.2, "count": [1, 2, 3]}
    assert beacon_material.precious == False
    assert beacon_material.motor.name == session.config.get("robz").name

    beacon_material.switch("default")
    # default should be loaded from file and be different
    # from previous values
    assert beacon_material.color == None
    assert beacon_material.specific_weight == None
    assert beacon_material.dimensions == None
    assert beacon_material.specific_weight == None
    assert beacon_material.precious == False
    assert beacon_material.motor.name == session.config.get("roby").name


def test_bad_name_for_beacon(session):
    bad = settings.ParametersWardrobe("bad")
    for name in r"!@#$%^&*()123804/`-+=,./".split():
        with pytest.raises(NameError):
            bad.to_beacon(name, "default")
        with pytest.raises(NameError):
            bad.from_beacon(name, "default")


def test_purge(beacon):
    purge_me = settings.ParametersWardrobe("purge_me")
    purge_me.switch("new_instance")
    connection = beacon._connection.get_redis_connection(db=0)
    assert connection.exists("parameters:purge_me")
    assert connection.exists("parameters:purge_me:default")
    assert connection.exists("parameters:purge_me:new_instance")
    purge_me.purge()
    assert not connection.exists("parameters:purge_me")
    assert not connection.exists("parameters:purge_me:default")
    assert not connection.exists("parameters:purge_me:new_instance")

    with pytest.raises(IOError):
        # try to access Wardrobe after purge will raise an exception
        purge_me.current_instance
