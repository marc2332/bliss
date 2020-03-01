# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from nexus_writer_service.subscribers import devices


def test_devices_shortnamemap():
    assert devices.shortnamemap([]) == {}
    assert devices.shortnamemap(["a:b:c"]) == {"a:b:c": "c"}
    assert devices.shortnamemap(["a:b:c", "a:b:d"]) == {"a:b:c": "c", "a:b:d": "d"}
    assert devices.shortnamemap(["a:b:c", "a:b:c", "a:b:d"]) == {
        "a:b:c": "c",
        "a:b:d": "d",
    }
    assert devices.shortnamemap(["a:b:c", "a:b:d", "c"]) == {
        "a:b:c": "b:c",
        "a:b:d": "d",
        "c": "c",
    }
    assert devices.shortnamemap(["a:b:c", "b:c:d", "b:c"]) == {
        "a:b:c": "a:b:c",
        "b:c:d": "d",
        "b:c": "b:c",
    }
    assert devices.shortnamemap(["a:b:c", "a:c"]) == {"a:b:c": "b:c", "a:c": "a:c"}
    assert devices.shortnamemap(["a:b:c", "b:c"]) == {"a:b:c": "a:b:c", "b:c": "b:c"}
    assert devices.shortnamemap(["b:a", "c:a"]) == {"b:a": "b:a", "c:a": "c:a"}
