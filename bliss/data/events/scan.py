# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.config import streaming_events

__all__ = ["EndScanEvent"]


class EndScanEvent(streaming_events.EndEvent):

    TYPE = b"END_SCAN"

    @classmethod
    def merge(cls, events):
        """Keep only the first event.

        :param list((index, raw)) events:
        :returns EndScanEvent:
        """
        return cls(raw=events[0][1])

    @property
    def description(self):
        """Used to generate EventData description"""
        return self.exception
