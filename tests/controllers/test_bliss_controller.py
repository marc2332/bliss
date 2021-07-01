# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from unittest import mock

from bliss.controllers.bliss_controller import BlissController
from bliss.controllers.bliss_controller_mockup import BCMockup, Operator, FakeItem

from bliss.config.plugins.bliss_controller import create_objects_from_config_node
from bliss.config.plugins.bliss_controller import create_object_from_cache
from bliss.config.plugins.bliss_controller import find_top_class_and_node

# test if no class specified at controller level !


def test_plugin_get_items_from_config(default_session):

    # load controllers
    bcmocks = {}
    for bcname in ["bcmock1", "bcmock2"]:
        bcmock = default_session.config.get(bcname)
        assert isinstance(bcmock, BCMockup)
        assert isinstance(bcmock, BlissController)
        assert bcmock.name == bcname
        bcmocks[bcname] = bcmock

    # get items, check class and owner
    it11 = default_session.config.get("item11")
    assert isinstance(it11, FakeItem)
    assert bcmocks["bcmock1"]._subitems[it11.name] is it11

    it12 = default_session.config.get("item12")
    assert isinstance(it12, FakeItem)
    assert bcmocks["bcmock1"]._subitems[it12.name] is it12

    # get items, check class and owner for a different cfg architecture (nested)
    it21 = default_session.config.get("item21")
    assert isinstance(it21, FakeItem)
    assert bcmocks["bcmock2"]._subitems[it21.name] is it21

    it211 = default_session.config.get("item211")
    assert isinstance(it211, FakeItem)
    assert bcmocks["bcmock2"]._subitems[it211.name] is it211

    # test error messages for unhandled items
    with pytest.raises(
        RuntimeError, match="Unable to obtain default_class_name from bcmock2"
    ):
        default_session.config.get("item22")

    with pytest.raises(
        RuntimeError, match="Unable to obtain default_module from bcmock2"
    ):
        default_session.config.get("item23")

    with pytest.raises(RuntimeError, match="Unable to obtain item item24 from bcmock2"):
        default_session.config.get("item24")

    # get items from an unloaded controller with no given name
    # check class and owner
    it31 = default_session.config.get("item31")
    assert isinstance(it31, FakeItem)
    assert it31.controller._subitems[it31.name] is it31

    it32 = default_session.config.get("item32")
    assert isinstance(it32, FakeItem)
    assert it32.controller._subitems[it32.name] is it32

    # check they have the same owner
    assert it31.controller is it32.controller

    # check generic controller name
    assert it31.controller.name.startswith("TestBCMockup_")

    # check that a top-level none-bliss_controller object can be loaded
    fakeop1 = default_session.config.get("fakeop1")
    assert isinstance(fakeop1, Operator)

    # check that a subitem of a none-bliss_controller cannot be loaded
    with pytest.raises(TypeError, match=" must be a ConfigItemContainer object"):
        default_session.config.get("not_allowed_item")


def test_plugin_prepared_subitems_configs(default_session):
    bcmock = default_session.config.get("bcmock")
    assert isinstance(bcmock, BCMockup)
    assert isinstance(bcmock, BlissController)
    assert bcmock.name == "bcmock"

    item_names = list(bcmock._subitems_config.keys())
    assert item_names == [
        "bctemp",
        "bcintime",
        "axis1",
        "axis2",
        "bccalcmot",
        "operator1",
        "operator2",
    ]

    cfgnode, pkey = bcmock._subitems_config["bctemp"]
    assert pkey == "counters"
    expected_cfg = {
        "name": "bctemp",
        "tag": "current_temperature",
        "mode": "MEAN",
        "unit": "°C",
        "convfunc": "2*x + 2",
    }
    assert cfgnode.to_dict() == expected_cfg

    cfgnode, pkey = bcmock._subitems_config["bcintime"]
    assert pkey == "counters"
    expected_cfg = {
        "name": "bcintime",
        "tag": "integration_time",
        "unit": "ms",
        "convfunc": "x * 1e3",
    }
    assert cfgnode.to_dict() == expected_cfg

    cfgnode, pkey = bcmock._subitems_config["axis1"]
    assert pkey == "axes"
    axis1 = default_session.config.get("axis1")
    expected_cfg = {"name": axis1, "tag": "xrot"}
    assert cfgnode.to_dict() == expected_cfg

    cfgnode, pkey = bcmock._subitems_config["axis2"]
    assert pkey == "axes"
    axis2 = default_session.config.get("axis2")
    expected_cfg = {"name": axis2, "tag": "yrot"}
    assert cfgnode.to_dict() == expected_cfg

    cfgnode, pkey = bcmock._subitems_config["operator1"]
    assert pkey == "operators"
    bctemp = default_session.config.get("bctemp")
    expected_cfg = {
        "name": "operator1",
        "input": bctemp,
        "factor": 2,
        "class": "bliss.controllers.bliss_controller_mockup.Operator",
    }
    assert cfgnode.to_dict() == expected_cfg

    cfgnode, pkey = bcmock._subitems_config["operator2"]
    assert pkey == "operators"
    bcintime = default_session.config.get("bcintime")
    expected_cfg = {
        "name": "operator2",
        "input": bcintime,
        "factor": 0.5,
        "class": "Operator",
    }
    assert cfgnode.to_dict() == expected_cfg


def test_plugin_items_loading_order(default_session):
    """ Check the loading order while importing the bcmock object and subitems.
        It tests the From config / From cache behavior.
        It tests the dereferencing behavior in those cases:
        - reference at controller level (ctrl_param: $foo)
        - reference at subitem level (item_param: $foo)
        - subitem as reference (name: $foo )
    """
    global from_config_counts
    global from_cache_counts

    from_config_counts = 0
    from_cache_counts = 0

    def wrap_create_objects_from_config_node(*args, **kwargs):
        global from_config_counts
        from_config_counts += 1
        return create_objects_from_config_node(*args, **kwargs)

    def wrap_create_object_from_cache(*args, **kwargs):
        global from_cache_counts
        from_cache_counts += 1
        return create_object_from_cache(*args, **kwargs)

    with mock.patch(
        "bliss.config.plugins.bliss_controller.create_objects_from_config_node",
        wraps=wrap_create_objects_from_config_node,
    ):
        with mock.patch(
            "bliss.config.plugins.bliss_controller.create_object_from_cache",
            wraps=wrap_create_object_from_cache,
        ):

            bcmock = default_session.config.get("bcmock")

            # === expected loading order ======
            # === From config: bcmock from bcmock   # ctrl init => ctrl config => energy: $robz
            # === From config: robz from test       # resolve $robz => robz controller init => robz cached
            # === From cache: robz from test        # robz from its cached controller
            # === Build item robz from test         # robz is returned by its controller
            # === Build item bctemp from bcmock     # bcmock loads its counters while initializing
            # === Build item bcintime from bcmock   # bcmock loads its counters while initializing

            assert from_config_counts == 2
            assert from_cache_counts == 1

            # === robz is already created and known by the Config
            # === so robz import should not increase config or cache counts
            robz = default_session.config.get("robz")
            assert from_config_counts == 2
            assert from_cache_counts == 1

            # === robz controller is already created and known by the Config
            # === so controller import should not increase config or cache counts
            robz_ctrl = default_session.config.get("test")
            assert robz.controller is robz_ctrl  # check 'test' is the owner of robz
            assert from_config_counts == 2
            assert from_cache_counts == 1

            # === bctemp already created so it can be returned directly by the controller
            bctemp = bcmock._get_subitem("bctemp")
            assert bctemp.name == "bctemp"
            # === but bctemp is still in cache for the Config/Plugin
            # === so bctemp import should come from cache
            bctemp2 = default_session.config.get("bctemp")
            assert from_config_counts == 2
            assert from_cache_counts == 2
            assert bctemp2 is bctemp  # check they are same instances

            # === operator1 is in cache too
            # === so operator1 import should come from cache
            # === $bctemp is resolved but it is already known by Config
            # === so bctemp dereferencing should not increase config or cache counts
            operator1 = default_session.config.get("operator1")
            assert from_config_counts == 2
            assert from_cache_counts == 3

            # === accessing operator1.input should not increase config or cache counts
            bctemp3 = operator1.input
            assert bctemp3 is bctemp2
            assert from_config_counts == 2
            assert from_cache_counts == 3

            # === operator2 is in cache too
            # === so operator2 import should come from cache
            # === $bcintime is resolved but still in Config cache
            # === so bcintime dereferencing should come from cache
            operator2 = default_session.config.get("operator2")
            assert from_config_counts == 2
            assert from_cache_counts == 5

            # === accessing operator2.input should not increase config or cache counts
            bcintime = operator2.input
            assert from_config_counts == 2
            assert from_cache_counts == 5
            # === importing bcintime should not increase config or cache counts
            bcintime2 = default_session.config.get("bcintime")
            assert from_config_counts == 2
            assert from_cache_counts == 5
            assert bcintime is bcintime2

            # === referenced axis1 still not resolved
            # === so getting it from bcmock should trigger
            # === a FromConfig from axis1 controller (which cache axis1)
            # === and a FromCache for the axis1 itself
            axis1 = bcmock.get_axis("axis1")
            assert from_config_counts == 3
            assert from_cache_counts == 6

            # === now axis1 from the config should not increase config or cache counts
            axis1b = default_session.config.get("axis1")
            assert axis1 is axis1b
            assert from_config_counts == 3
            assert from_cache_counts == 6

            # === axis2 was cached at the previous step while resolving axis1
            # === so now axis2 from config should only increase cache counts
            axis2 = default_session.config.get("axis2")
            assert from_config_counts == 3
            assert from_cache_counts == 7

            # === axis2 is still not loaded within bcmock
            assert bcmock._subitems.get("axis2") is None
            # === but accessing it from the bcmock should
            # === not increase config or cache counts
            axis2b = bcmock.get_axis("axis2")
            assert from_config_counts == 3
            assert from_cache_counts == 7
            # === but it should register it into bcmock subitems
            assert bcmock._subitems.get("axis2") is axis2
            assert axis2b is axis2

            # === accessing bcmock.calc_mot property will
            # === resolve $calc_mot2.controller (only now on first property call)
            # === it will increase config count for calc_mot2 controller
            # === calc_mot forces all axes creation at ctrl init so
            # === it will dereference $calc_mot1
            # === it will increase config count for calc_mot1 controller
            # === it will dereference $roby
            # === it will increase config count for roby controller
            # === motor controller does not force init of all axes so
            # === it will increase config cache for roby
            # === then back to upper levels
            # === it will increase config cache for calc_mot1
            # === it will increase config cache for calc_mot2

            calc_ctrl = bcmock.calc_mot
            assert from_config_counts == 6
            assert from_cache_counts == 10

            # === now importing calc_mot2 should not increase config or cache counts
            calc_mot2 = default_session.config.get("calc_mot2")
            calc_mot2b = calc_ctrl.get_axis("calc_mot2")
            assert from_config_counts == 6
            assert from_cache_counts == 10
            assert calc_mot2 is calc_mot2b
            assert calc_ctrl is calc_mot2.controller

            # === access bccalcmot increase config count for its controller
            # === then it resolves $roby but it is already created so
            # === only one cache count for bccalcmot item
            bccalcmot = bcmock.get_axis("bccalcmot")
            assert from_config_counts == 7
            assert from_cache_counts == 11

            # clean all calc controllers involved
            bccalcmot.controller.close()
            calc_ctrl.close()
            calc_mot1 = default_session.config.get("calc_mot1")
            calc_mot1.controller.close()


def test_plugin_items_initialized_only_once(default_session):
    """ load all test session objects and check that those going through
        bliss controller plugin are never created twice.
        (see FromConfig for the controllers and FromCache for the subitems)   
    """

    global from_config_counts
    global from_cache_counts

    from_config_counts = []
    from_cache_counts = []

    def wrap_create_objects_from_config_node(cfg_obj, cfg_node):
        global from_config_counts

        klass, ctrl_node = find_top_class_and_node(cfg_node)
        ctrl_name = ctrl_node.get("name")
        if ctrl_name is None:
            ctrl_name = f"{klass.__name__}_{ctrl_node.md5hash()}"

        if ctrl_name in from_config_counts:
            raise RuntimeError(f"{ctrl_name} has been already created once!")
        from_config_counts.append(ctrl_name)

        return create_objects_from_config_node(cfg_obj, cfg_node)

    def wrap_create_object_from_cache(config, name, bctrl):
        global from_cache_counts

        if name in from_cache_counts:
            raise RuntimeError(f"{name} has been already created once!")
        from_cache_counts.append(name)

        return create_object_from_cache(config, name, bctrl)

    with mock.patch(
        "bliss.config.plugins.bliss_controller.create_objects_from_config_node",
        wraps=wrap_create_objects_from_config_node,
    ):
        with mock.patch(
            "bliss.config.plugins.bliss_controller.create_object_from_cache",
            wraps=wrap_create_object_from_cache,
        ):

            obj_list = [
                "beamstop",
                "att1",
                "MG1",
                "MG2",
                "bad",
                "calc_mot1",
                "calc_mot2",
                "custom_axis",
                "diode",
                "diode0",
                "diode1",
                "diode2",
                "diode3",
                "diode4",
                "diode5",
                "diode6",
                "diode7",
                "diode8",
                "diode9",
                "heater",
                "hook0",
                "hook1",
                "hooked_error_m0",
                "hooked_m0",
                "hooked_m1",
                "integ_diode",
                "jogger",
                "m0",
                "m1",
                "m1enc",
                "omega",
                "roby",
                "robz",
                "robz2",
                "s1b",
                "s1d",
                "s1f",
                "s1hg",
                "s1ho",
                "s1u",
                "s1vg",
                "s1vo",
                "sample_regulation",
                "sample_regulation_new",
                "soft_regul",
                "sensor",
                "sim_ct_gauss",
                "sim_ct_gauss_noise",
                "sim_ct_flat_12",
                "sim_ct_rand_12",
                "test",
                "test_mg",
                "thermo_sample",
                "transfocator_simulator",
            ]

            for objname in obj_list:
                default_session.config.get(objname)

            # print(from_config_counts)
            # print(from_cache_counts)


def test_bliss_controller(default_session):
    bcmock = default_session.config.get("bcmock")
    bcmock.name
    bcmock.config
    bcmock.counters
    bcmock.axes
