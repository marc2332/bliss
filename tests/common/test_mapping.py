# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.common.mapping import Map
from bliss.common.logtools import create_logger_name
from bliss.common import session as session_module
import networkx as nx
import logging
import sys


class SimpleNode:
    def __init__(self, attr=None):
        self.arg1 = "arg1"
        self.arg2 = "arg2"
        self.partial_id = str(id(self))[:4]
        if attr:
            self.attr = attr


@pytest.fixture
def beamline():
    """
    Creates a new graph
    """
    map = Map()

    map.register("session")
    map.register("controllers", parents_list=["session"])
    map.register("comms", parents_list=["session"])
    map.register("counters", parents_list=["session"])
    map.register("axes", parents_list=["session"])
    return map


@pytest.fixture
def complex_beamline(beamline):
    beamline.register("Contr_1", tag="C1")
    beamline.register("Contr_2", tag="C2")  # should be under devices
    beamline.register("Contr_3", tag="C3")  # should be under devices
    beamline.register("m1")
    beamline.register(
        "Axis_1", parents_list=["Contr_1"], children_list=["m0"], tag="Axis_1"
    )
    beamline.register(
        "Axis_2",
        parents_list=["Contr_1"],
        children_list=["m1", "m2", "m3"],
        tag="Axis_2",
    )
    beamline.register("m0")
    beamline.register("Serial_1", parents_list=["Contr_1", "comms"], tag="Serial_1")
    beamline.register("TcpIp", parents_list=["Contr_2", "comms"], tag="TcpIp")

    class A:
        pass

    a = A()
    beamline.register(a)
    assert create_logger_name(beamline.G, id(a)) == "session.controllers.A"

    return beamline


def test_starting_map_length(beamline):
    """
    At the beginning there should be % nodes:
    BEAMLINE, DEVICES, SESSIONS, COMMS, COUNTERS
    """
    assert len(beamline.G) == 5


def test_path_to_non_existing_node(beamline):
    with pytest.raises(nx.exception.NodeNotFound):
        beamline.shortest_path("session", "non_existing_node")


def test_path_to_with_non_existing_path(beamline):
    with pytest.raises(nx.exception.NetworkXNoPath):
        beamline.shortest_path("controllers", "comms")


def test_find_children(beamline):
    children = beamline.find_children("session")
    assert isinstance(children, list)
    assert len(list(beamline.find_children("session"))) == 4


def test_find_predecessor(beamline):
    predecessors = beamline.find_predecessors("counters")
    assert isinstance(predecessors, list)
    _pre = list(predecessors)
    assert len(_pre) == 1
    assert _pre.pop() == "session"


def test_find_shortest_path(beamline):
    """this should be: beamline -> devices -> MotorControllerForM0 -> motor0"""
    beamline.register("motor0", parents_list=["MotorControllerForM0"])
    beamline.register("MotorControllerForM0")
    path = beamline.shortest_path("session", "motor0")
    assert isinstance(path, list)
    assert len(path) == 4


def test_bad_parents_list(beamline):
    with pytest.raises(TypeError):
        beamline.register("motor0", parents_list="MotorControllerForM0")


def test_populate_self_defined_attributes(beamline):
    beamline.register(
        "motor0", parents_list=["MotorControllerForM0"], speed=100, power="0.3kW"
    )
    assert beamline.G.nodes["motor0"]["speed"] == 100
    assert beamline.G.nodes["motor0"]["power"] == "0.3kW"


def test_find_no_path(beamline):
    """this motor0 is attached to controllers, so there is no link with counters"""
    beamline.register("motor0")
    with pytest.raises(nx.exception.NetworkXNoPath):
        beamline.shortest_path("axes", "motor0")


def test_find_shortest_path_reverse_order(beamline):
    """
    reverting the order of device mapping, the path should be the same
    this should be: beamline -> controllers -> MotorControllerForM0 -> motor0
    """
    beamline.register("MotorControllerForM0")
    beamline.register("motor0", parents_list=["MotorControllerForM0"])
    path = beamline.shortest_path("session", "motor0")
    assert isinstance(path, list)
    assert len(path) == 4


def test_find_shortest_path_parallel(beamline):
    """
     this should be: beamline -> devices -> MotorControllerForM0
                                         -> motor0
    """
    beamline.register("motor0")
    beamline.register("MotorControllerForM0")
    path = beamline.shortest_path("session", "motor0")
    assert isinstance(path, list)
    assert len(path) == 3
    path = beamline.shortest_path("session", "MotorControllerForM0")
    assert isinstance(path, list)
    assert len(path) == 3


def test_remap_children(beamline):
    """
    this should be: beamline -> controllers -> MotorControllerForM0 -> motor0
    creating before motor0 that will be child of devices
    then adding MotorControllerForM0 that will have motor0 as a child
    motor0 should remap removing the connection device -> motor0
    """
    beamline.register("motor0")
    beamline.register("MotorControllerForM0", children_list=["motor0"])
    path = beamline.shortest_path("session", "motor0")
    assert len(path) == 4


def test_cant_delete_non_existing_node(beamline):
    """node does not exists, this should return false"""
    assert not beamline.delete("fakenode")


def test_complex_map(complex_beamline):
    """children of comms should be 2"""
    assert len(list(complex_beamline.find_children("comms"))) == 2


def test_complex_map_remove_children(complex_beamline):
    """find predecessors of Contr_1, should be devices"""
    _pre = list(complex_beamline.find_predecessors("Contr_1"))
    assert len(_pre) == 1
    assert _pre.pop() == "controllers"
    # finding children of Contr_1, should be Serial, Ax1, Ax2
    _children = complex_beamline.find_children("Contr_1")
    assert isinstance(_children, list)
    list_children = list(_children)
    assert len(list_children) == 3
    assert "Axis_1" in list_children
    assert "Axis_2" in list_children
    assert "Serial_1" in list_children
    # deleting devices node, now should be beamline
    complex_beamline.delete(id_="controllers")
    _pre = list(complex_beamline.find_predecessors("Contr_1"))
    assert len(_pre) == 1
    assert _pre.pop() == "session"


def test_format_node_1(beamline):
    tn = SimpleNode(attr="1234")
    beamline.register(tn, tag="myname")  # under devices
    assert beamline.format_node(id(tn), format_string="inst.attr->id") == "1234"
    assert (
        beamline.format_node(id(tn), format_string="inst.partial_id->id")
        == str(id(tn))[:4]
    )
    assert beamline.format_node(id(tn), format_string="inst.arg1->name") == "arg1"
    assert not hasattr(beamline.G.node[id(tn)], "name")
    assert beamline.format_node(id(tn), format_string="name->inst.arg1") == "arg1"
    assert beamline.format_node("session", format_string="inst") == "session"


def test_check_formatting_1(beamline):
    """Should plot only the id as fakearg doesn't exists"""
    beamline._update_key_for_nodes("fakearg+id->name", dict_key="mykey")
    for el in beamline.G:
        assert beamline.G.node[el]["mykey"] == str(el)


def test_check_formatting_2(beamline):
    """Should plot only the id as fakearg doesn't exists"""
    beamline._update_key_for_nodes("fakearg+id->name")
    for el in beamline.G:
        assert beamline.G.node[el]["label"] == str(el)


def test_check_formatting_3(beamline):
    tn = SimpleNode(attr="1234")
    beamline.register(tn, tag="myname")  # under devices
    beamline._update_key_for_nodes("tag->name->id", dict_key="ee")
    for el in beamline.G:
        if el == id(tn):  # SimpleNode should have a tag=myname
            assert beamline.G.node[el]["ee"] == "myname"
        else:
            # name not found, should find id
            assert beamline.G.node[el]["ee"] == beamline.G.node[el]["tag"]


def test_bad_formatting(beamline):
    beamline._update_key_for_nodes("asda11@@@1", dict_key="ee")
    for el in beamline.G:
        assert "ee" in beamline.G.node[el]  # check existance
        assert beamline.G.node[el]["ee"] == ""  # check isnull string
    beamline._update_key_for_nodes("!!!!", dict_key="ee")
    for el in beamline.G:
        assert "ee" in beamline.G.node[el]
        assert beamline.G.node[el]["ee"] == ""
    beamline._update_key_for_nodes("_2aasdad1", dict_key="ee")
    for el in beamline.G:
        assert "ee" in beamline.G.node[el]
        assert beamline.G.node[el]["ee"] == ""
    beamline._update_key_for_nodes("2", dict_key="ee")
    for el in beamline.G:
        assert "ee" in beamline.G.node[el]
        assert beamline.G.node[el]["ee"] == ""


def test_deleted_instance(beamline):
    """
    Check auto removal of nodes
    """
    tn = SimpleNode(attr="1234")
    id_tn = id(tn)
    beamline.register(tn, tag="myname")  # under devices
    assert id_tn in beamline.G
    del tn
    assert id_tn not in beamline.G


def test_session_map(beacon, s1hg, roby):
    session = session_module.get_current()
    m = session.map
    sr = session.config.get("sample_regulation")
    heater = session.config.get("heater")
    # m.draw_pygraphviz()

    assert len(m) == 33
    axes = list(m.find_children("axes"))
    assert id(roby) in axes
    assert id(s1hg) in axes
    assert len(axes) == 2
    counters = list(m.find_children("counters"))
    assert id(heater) in counters
    assert len(counters) == 1
    slits_children = m.find_children(id(s1hg.controller))
    for real_axis in s1hg.controller.reals:
        assert id(real_axis) in slits_children
    assert id(s1hg) in slits_children
    s1hg_pred = m.find_predecessors(id(s1hg))
    assert len(s1hg_pred) == 2
    assert id(s1hg.controller) in s1hg_pred
    sr_children = m.find_children(id(sr))
    assert len(sr_children) == 2
    inp, outp = sr.input, sr.output
    assert outp is heater
    assert id(inp) in sr_children
    assert id(outp) in sr_children
    inp_pred = m.find_predecessors(id(inp))
    outp_pred = m.find_predecessors(id(outp))
    outp_pred.remove("counters")
    assert set(outp_pred) == set(inp_pred)
    assert "motion_hooks" in m.find_children("controllers")
    motion_hooks_children = m.find_children("motion_hooks")
    assert len(motion_hooks_children) == 3
    hooked_m0 = beacon.get("hooked_m0")
    hooked_m0_pred = m.find_predecessors(id(hooked_m0))
    assert "axes" in hooked_m0_pred
    hooked_m0_pred.remove("axes")
    assert set([m.find_predecessors(hm_pred)[0] for hm_pred in hooked_m0_pred]) == set(
        ["controllers", "motion_hooks"]
    )


def test_bad_function_on_trigger_update(beamline):
    def bad_func(graph):
        raise NotImplementedError

    beamline.add_map_handler(bad_func)

    with pytest.raises(NotImplementedError):
        beamline.register("new node")


def test_create_submap_1(complex_beamline):
    sub_G = nx.DiGraph()
    complex_beamline.create_submap(sub_G, "comms")
    assert len(sub_G) == 3
    for node in "comms TcpIp Serial_1".split():
        assert node in sub_G


def test_create_submap_2(complex_beamline):
    sub_G = nx.DiGraph()
    complex_beamline.create_submap(sub_G, "Contr_1")
    assert len(sub_G) == 8
    for node in "Contr_1 Serial_1 Axis_1 Axis_2 m0 m1 m2 m3".split():
        assert node in sub_G


def test_create_submap_3(complex_beamline):
    sub_G = nx.DiGraph()
    # submap from the root node should be equal to the map itself
    complex_beamline.create_submap(sub_G, "session")
    assert len(sub_G) == len(complex_beamline.G)
    for node in sub_G.nodes:
        assert node in complex_beamline.G


def test_create_partial_map_1(complex_beamline):
    sub_G = nx.DiGraph()
    complex_beamline.create_partial_map(sub_G, "Contr_2")
    assert len(sub_G) == 4
    for node in "session controllers Contr_2 TcpIp".split():
        assert node in sub_G


def test_create_partial_map_2(complex_beamline):
    sub_G = nx.DiGraph()
    complex_beamline.create_partial_map(sub_G, "Axis_2")
    assert len(sub_G) == 7
    for node in "session controllers Contr_1 Axis_2 m1 m2 m3".split():
        assert node in sub_G


def test_non_cyclic_ref(beacon):
    m = Map()

    class Cnt:
        class Counter:
            def __init__(self, name, mode):
                self.name = name
                self.mode = mode

        def __init__(self):
            self.in_set_mode = False
            self.mode = None
            self.__counter = list()

        def set_mode(self, mode):
            if self.mode == mode:
                return

            if self.in_set_mode:
                return
            print(f"set_mode {mode} {id(self)}")
            self.in_set_mode = True
            while self.__counter:
                cnt = self.__counter.pop(0)
                print(f"remove {cnt.name} {id(self)} {sys.getrefcount(cnt)}")
            for i in range(10):
                print(f"create counter {i} {id(self)}")
                c = Cnt.Counter(f"counter {i}", mode)
                m.register(c)
                self.__counter.append(c)
            self.in_set_mode = False
            self.mode = mode

    def update_mode(G):
        for node in list(G):
            ref = G.node[node].get("instance")
            try:
                inst = ref()
            except:
                continue
            if isinstance(inst, Cnt):
                inst.set_mode(current_mode)

    m.add_map_handler(update_mode)
    cnts = list()
    for current_mode in ["bla", "truc", "chose", "hello", "mario"]:
        print(f"create cnt {current_mode}")
        cnt = Cnt()
        print(f"register cnt {current_mode}")
        m.register(cnt)
        cnts.append(cnt)


#########################  MANUAL TESTING  ###################################


def manual_test_draw_matplotlib(complex_beamline):
    complex_beamline.map_draw_matplotlib(format_node="tag+name->name->class")


def manual_test_draw_pygraphviz(complex_beamline):
    complex_beamline.map_draw_pygraphviz(format_node="name->tag->id->class")
