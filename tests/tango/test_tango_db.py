# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.conductor import client
from bliss.common.tango import Database


def test_tangodb_getters(beacon, dummy_tango_server):
    device_fqdn, dev_proxy = dummy_tango_server
    db = Database()

    # Dummy device info
    domain = "id00"
    family = "tango"
    name = "dummy"
    class_name = "Dummy"
    server = "dummy_tg_server"
    server_instances = ["dummy", "dummy2"]
    server_name = f"{server}/{name}"
    obj_names = [f"{domain}/{family}/{name}" for name in server_instances]
    dev_name = [f"{domain}.{family}.{name}" for name in server_instances]
    alias = "dummy_alias"
    serv_names = [f"{server}/{server_instance}" for server_instance in server_instances]
    dserver_names = [f"dserver/{serv_name}" for serv_name in serv_names]
    properties = {"dummy_property1": "dummy_value1", "dummy_property2": ""}
    cls_properties = {
        "dummy_cls_property1": "dummy_cls_value1",
        "dummy_cls_property2": "",
    }

    hosts = list(db.get_host_list())
    assert len(hosts) == 1
    host = hosts[0].lower()

    # TODO: possible case change or "localhost" instead of host name
    hosts = [host, "localhost"]
    result = db.get_db_host().lower()
    assert result in hosts
    result = db.get_dev_host().lower()
    assert result in hosts

    result = db.get_server_name_list()
    assert server in result

    result = db.get_server_list()
    assert all(serv_name in result for serv_name in serv_names)

    result = db.get_host_server_list(host)
    assert list(result) == [server_name]

    result = db.get_host_server_list("*")
    assert len(result) == 1
    assert list(result) == [server_name]

    result = db.get_instance_name_list(server)
    assert list(result) == server_instances

    result = db.get_instance_name_list("*")
    assert all(serv_instance in result for serv_instance in server_instances)

    for serv_name in serv_names:
        result = db.get_server_class_list(serv_name)
        assert list(result) == [class_name]

    result = db.get_server_class_list("*")
    assert class_name in result
    assert "DServer" not in result

    result = db.get_class_list(class_name)
    assert list(result) == [class_name]

    result = db.get_class_list("*")
    assert class_name in result
    assert "DServer" in result

    for i, serv_name in enumerate(serv_names):
        obj_name = obj_names[i]

        result = db.get_device_class_list(serv_name)
        assert list(result) == [obj_name, class_name]
        result = db.get_device_name(serv_name, class_name)
        assert list(result) == [obj_name]
        result = db.get_device_name(serv_name, "*")
        assert list(result) == [obj_name]

    result = db.get_device_class_list("*")
    assert not result

    result = db.get_device_name("*", class_name)
    assert all(obj_name in result for obj_name in obj_names)

    result = db.get_device_name("*", "*")
    assert all(obj_name in result for obj_name in obj_names)

    result = db.get_device_exported_for_class(class_name)
    assert list(result) == [obj_names[0]]  # only first dummy server is started

    result = db.get_device_exported_for_class("*")
    assert obj_names[0] in result

    result = db.get_device_exported("*")
    assert len(result) == 2
    assert set(result) == {obj_names[0], dserver_names[0]}

    result = db.get_device_family("*")
    assert family in result

    result = db.get_device_domain("*")
    assert domain in result

    # in next checks, only first dummy server is used
    obj_name = obj_names[0]
    serv_name = serv_names[0]

    result = db.get_class_for_device(obj_name)
    assert result == class_name

    result = db.get_device_property_list(obj_name, "*")
    assert len(result) == len(properties)
    assert set(result) == set(properties.keys())

    result = db.get_device_property(obj_name, list(properties.keys()))
    result = {k: v[0] for k, v in result.items()}
    assert result == properties

    result = db.get_device_property(obj_name, next(iter(properties.keys())))
    result = {k: v[0] for k, v in result.items()}
    assert result == dict([next(iter(properties.items()))])

    result = db.get_class_property_list(class_name)
    assert len(result) == len(cls_properties)
    assert set(result) == set(cls_properties.keys())

    result = db.get_class_property(class_name, list(cls_properties.keys()))
    result = {k: v[0] for k, v in result.items()}
    assert result == cls_properties

    result = db.get_class_property(class_name, next(iter(cls_properties.keys())))
    result = {k: v[0] for k, v in result.items()}
    assert result == dict([next(iter(cls_properties.items()))])

    result = db.get_device_alias(alias)
    assert result == obj_name

    result = db.get_device_from_alias(alias)
    assert result == obj_name

    result = db.get_alias(obj_name)
    assert result == alias

    result = db.get_alias_from_device(obj_name)
    assert result == alias

    result = db.get_device_alias_list("*")
    assert alias in result

    result = db.get_device_member("*")
    assert name in result
    assert alias in result

    info = db.get_device_info(obj_name)
    assert info.class_name == class_name
    assert info.ds_full_name == serv_name
    assert info.name == obj_name


def test_tangodb_setters(beacon, dummy_tango_server):
    device_fqdn, dev_proxy = dummy_tango_server
    db = Database()

    # Dummy device info
    domain = "id00"
    family = "tango"
    name = "dummy"
    class_name = "Dummy"
    server = "dummy_tg_server"
    server_instance = "dummy"
    dev_name = f"{domain}.{family}.{name}"
    obj_name = f"{domain}/{family}/{name}"
    alias = "dummy_alias"
    serv_name = f"{server}/{server_instance}"
    dserver_name = f"dserver/{serv_name}"

    result = db.get_device_property(obj_name, "dummy_property1")
    assert list(result["dummy_property1"]) == ["dummy_value1"]

    db.put_device_property(obj_name, {"dummy_property1": ""})
    result = db.get_device_property(obj_name, "dummy_property1")
    assert list(result["dummy_property1"]) == [""]

    # TODO: not supported
    # db.delete_device_property(obj_name, "dummy_property1")
    # result = db.get_device_property(obj_name, "dummy_property1")
    # assert not result["dummy_property1"]

    result = db.get_class_property(class_name, "dummy_cls_property1")
    assert list(result["dummy_cls_property1"]) == ["dummy_cls_value1"]

    db.put_class_property(class_name, {"dummy_cls_property1": ""})
    result = db.get_class_property(class_name, "dummy_cls_property1")
    assert list(result["dummy_cls_property1"]) == [""]

    # TODO: not supported
    # db.delete_class_property(class_name, "dummy_cls_property1")
    # result = db.get_class_property(class_name, "dummy_cls_property1")
    # assert not result["dummy_cls_property1"]


def test_issue2845(beacon, beacon_directory, dummy_tango_server2):
    device_fqdn, dev_proxy = dummy_tango_server2
    db = Database()

    # Dummy device info
    domain = "id00"
    family = "tango"
    name = "dummy2"
    obj_name = f"{domain}/{family}/{name}"

    assert not db.get_device_property(obj_name, "dummy_property1")["dummy_property1"]
    test_file_contents = client.get_text_file("tango/dummy.yml")
    assert test_file_contents.endswith(
        "tango_name: id00/tango/dummy2\n    properties:\n  personal_name: dummy2\n  server: dummy_tg_server\n"
    )

    db.put_device_property(obj_name, {"dummy_property1": "test"})
    result = db.get_device_property(obj_name, "dummy_property1")
    assert list(result["dummy_property1"]) == ["test"]

    test_file_contents = client.get_text_file("tango/dummy.yml")
    assert test_file_contents.endswith(
        "tango_name: id00/tango/dummy2\n    properties:\n      dummy_property1: test\n  personal_name: dummy2\n  server: dummy_tg_server\n"
    )
