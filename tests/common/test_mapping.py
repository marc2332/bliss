# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.common.mapping import Map
from bliss.common.logtools import create_logger_name
import networkx as nx
import logging


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


def test_failed_delete(beamline):
    """node does not exists, this should raise an exception"""
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


#########################  MANUAL TESTING  ###################################


def manual_test_draw_matplotlib(complex_beamline):
    complex_beamline.map_draw_matplotlib(format_node="tag+name->name->class")


def manual_test_draw_pygraphviz(complex_beamline):
    complex_beamline.map_draw_pygraphviz(format_node="name->tag->id->class")
