# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import collections
from bliss.config.settings import QueueSetting
from bliss.common.data_manager import DataNode

class Dataset0D(DataNode):
    class DataChannel(object):
        def __init__(self,channel_db_name) :
            cnx = node.get_default_connection()
            self._queue = QueueSetting(channel_db_name,
                                       connection=cnx).get_proxy()
        def get(self,from_index,to_index = None):
            if to_index is None:
                return self._queue[from_index]
            else:
                return self._queue[from_index:to_index]

    def __init__(self,name,**keys):
        DataNode.__init__(self,'zerod',name,**keys)
        cnx = self.db_connection
        self._channels_name = QueueSetting('%s_channels' % self.db_name(),connection=cnx)
        self._channels = {}
        for channel_name in self._channels_name:
            self._channels[channel_name] = QueueSetting('%s_%s' % (self.db_name(),channel_name),
                                                        connection=cnx)
    def channel_name(self) :
        return self._channels.get()

    def store(self,signal,event_dict) :
        if signal == "new_data":
            channel_data = event_dict.get("channel_data")
            if channel_data is None:
                #warning
                return
            for channel_name,data in channel_data.iteritems():
                queue = self._channels.get(channel_name)
                if queue is None:
                    self._channels_name.append(channel_name)
                    queue = QueueSetting('%s_%s' % (self.db_name(),channel_name),
                                         connection=self.db_connection)
                    queue.extend(data)
                    self._channels[channel_name] = queue
                else:
                    queue.extend(data)

    #@brief get data channel object
    def get_channel(self,channel_name = None) :
        if channel_name is None:
            channel_name = self._channels[0]
        channel_db_name = '%s_%s' % (self.db_name(),channel_name)
        return Dataset0D.DataChannel(channel_db_name)

    def set_ttl(self):
        DataNode.set_ttl(self)
        for channel in self._channels.itervalues():
            channel.ttl(DataNode.default_time_to_live)
