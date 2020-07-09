# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import streaming_events

__all__ = ["NewNodeEvent"]


class NewNodeEvent(streaming_events.StreamEvent):

    TYPE = b"NEW_NODE"
    DB_KEY = b"db_name"

    def init(self, db_name):
        self.db_name = db_name

    def _encode(self):
        raw = super()._encode()
        raw[self.DB_KEY] = self.encode_string(self.db_name)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.db_name = self.decode_string(raw[self.DB_KEY])
