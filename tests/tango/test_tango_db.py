# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.common.tango import Database


def dbdatum_to_list(dbdatum):
    return [item for item in dbdatum]


def dbdatum_to_set(dbdatum):
    return {item for item in dbdatum}


def test_tangodb_getters(beacon, dummy_tango_server):
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
    properties = {"dummy_property1": "dummy_value1", "dummy_property2": "dummy_value2"}

    hosts = dbdatum_to_list(db.get_host_list())
    assert len(hosts) == 1
    host = hosts[0]

    result = db.get_db_host()
    assert (
        result.lower() == host.lower()
    )  # for some reason, it happened to have some upper case characters here!

    result = db.get_dev_host()
    assert (
        result.lower() == host.lower()
    )  # for some reason, it happened to have some upper case characters here!

    result = db.get_server_name_list()
    assert server in result

    result = db.get_server_list()
    assert serv_name in result

    result = db.get_host_server_list(host)
    assert dbdatum_to_list(result) == [serv_name]

    result = db.get_host_server_list("*")
    assert len(result) == 1
    assert dbdatum_to_list(result) == [serv_name]

    result = db.get_instance_name_list(server)
    assert dbdatum_to_list(result) == [server_instance]

    result = db.get_instance_name_list("*")
    assert server_instance in result

    result = db.get_server_class_list(serv_name)
    assert dbdatum_to_list(result) == [class_name]

    result = db.get_server_class_list("*")
    assert class_name in result
    assert "DServer" not in result

    result = db.get_class_list(class_name)
    assert dbdatum_to_list(result) == [class_name]

    result = db.get_class_list("*")
    assert class_name in result
    assert "DServer" in result

    result = db.get_device_class_list(serv_name)
    assert dbdatum_to_list(result) == [obj_name, class_name]

    result = db.get_device_class_list("*")
    assert not result

    result = db.get_device_name(serv_name, class_name)
    assert dbdatum_to_list(result) == [obj_name]

    result = db.get_device_name("*", class_name)
    assert dbdatum_to_list(result) == [obj_name]

    result = db.get_device_name(serv_name, "*")
    assert dbdatum_to_list(result) == [obj_name]

    result = db.get_device_name("*", "*")
    assert obj_name in result

    result = db.get_device_exported_for_class(class_name)
    assert dbdatum_to_list(result) == [obj_name]

    result = db.get_device_exported_for_class("*")
    assert obj_name in result

    result = db.get_device_exported("*")
    assert len(result) == 2
    assert dbdatum_to_set(result) == {obj_name, dserver_name}

    result = db.get_device_family("*")
    assert family in result

    result = db.get_device_domain("*")
    assert domain in result

    result = db.get_class_for_device(obj_name)
    assert result == class_name

    result = db.get_device_property_list(obj_name, "*")
    assert len(result) == len(properties)
    assert dbdatum_to_set(result) == set(properties.keys())

    result = db.get_device_property(obj_name, list(properties.keys()))
    result = {k: v[0] for k, v in result.items()}
    assert result == properties

    result = db.get_device_property(obj_name, next(iter(properties.keys())))
    result = {k: v[0] for k, v in result.items()}
    assert result == dict([next(iter(properties.items()))])

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
