# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
from bliss.common import proxy
from bliss.controllers import moco
from . import register_local_client_callback


class _LocalMoco(proxy.Proxy):
    __slots__ = list(proxy.Proxy.__slots__) + ["counters_controller"]

    def __init__(self, client, port, config):
        super().__init__(None)
        self.__target__ = client

        self.counters_controller = moco.MocoCounterController(self)
        for cnt_config in config.get("counters", []):
            counter_name = cnt_config.get("counter_name")
            moco.MocoCounter(counter_name, cnt_config, self.counters_controller)

    @property
    def counters(self):
        return self.counters_controller.counters


def init():
    register_local_client_callback(moco.Moco, _LocalMoco)
