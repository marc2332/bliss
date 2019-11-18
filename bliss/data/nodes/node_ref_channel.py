# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.nodes.channel import ChannelDataNode
from bliss.data.node import get_node, get_nodes
import numpy


class NodeRefChannel(ChannelDataNode):
    """
    A data node that stores references to other DataNodes. It is intened to be used to
    keep references e.g. of individual scans to group them together as one group or sequence 
    of scans.
    """

    _NODE_TYPE = "node_ref_channel"

    def get(self, from_index, to_index=None):
        """
        Return the data nodes according to the references stored in this channel 

        **from_index** from which image index you want to get
        **to_index** to which index you want images
            if to_index is None => only one image which as index from_index
            if to_index < 0 => to the end of acquisition
        """
        if to_index is None:
            return get_node(ChannelDataNode.get(self, from_index))
        else:
            return get_nodes(*ChannelDataNode.get(self, from_index, to_index))

    def store(self, event_dict):
        self._create_queue()

        data = event_dict.get("data")
        self.info.update(event_dict["description"])
        shape = event_dict["description"]["shape"]

        if type(data) is numpy.ndarray:
            if len(shape) == data.ndim:
                self._queue.append(data)
            else:
                self._queue.extend(data)
        elif type(data) is list or type(data) is tuple:
            self._queue.extend(data)
        else:
            self._queue.append(data)
