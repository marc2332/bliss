# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.nodes.channel import ChannelDataNode
from bliss.data.node import get_node, get_nodes
from bliss.data.events import EventData
import numpy


class NodeRefChannel(ChannelDataNode):
    """
    A data node that stores references to other DataNodes. It is intened to be used to
    keep references e.g. of individual scans to group them together as one group or sequence 
    of scans.
    """

    _NODE_TYPE = "node_ref_channel"

    def decode_raw_events(self, events):
        event_data = super().decode_raw_events(events)
        nodes = get_nodes(*event_data.data)
        return EventData(
            first_index=event_data.first_index,
            data=nodes,
            description=event_data.description,
            block_size=event_data.block_size,
        )
