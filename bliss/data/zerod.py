# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import collections
from bliss.config.settings import QueueSetting
from bliss.data.node import DataNode


class Dataset0D(DataNode):
    class DataChannel(object):
        def __init__(self, channel_db_name, cnx):
            self._queue = QueueSetting(channel_db_name,
                                       connection=cnx)

        def get(self, from_index, to_index=None):
            if to_index is None:
                return self._queue[from_index]
            else:
                return self._queue[from_index:to_index]

        def __len__(self):
            return self._queue.__len__()

    def __init__(self, name, **keys):
        DataNode.__init__(self, 'zerod', name, **keys)
        cnx = self.db_connection
        self._channels_name = QueueSetting(
            '%s_channels' % self.db_name(), connection=cnx)
        self._channels = {}
        for channel_name in self._channels_name:
            self._channels[channel_name] = QueueSetting('%s_%s' % (self.db_name(), channel_name),
                                                        connection=cnx)

    def channels_name(self):
        return list(self._channels_name)

    def store(self, signal, event_dict):
        if signal == "new_data":
            channel_data = event_dict.get("channel_data")
            if channel_data is None:
                # warning
                return
            for channel_name, data in channel_data.iteritems():
                if data.size == 0:
                    continue
                queue = self._channels.get(channel_name)
                if queue is None:
                    self._channels_name.append(channel_name)
                    queue = QueueSetting('%s_%s' % (self.db_name(), channel_name),
                                         connection=self.db_connection)
                    self._channels[channel_name] = queue
                try:
                    iter(data)
                except:
                    queue.append(data)
                else:
                    queue.extend(data)

    #@brief get data channel object
    def get_channel(self, channel_name=None, check_exists=True, cnx=None):
        if channel_name is None:
            channel_name = self._channels_name[0]
        elif check_exists and channel_name not in self._channels_name:
            raise ValueError("Unknown channel %s" % channel_name)

        channel_db_name = '%s_%s' % (self.db_name(), channel_name)
        return Dataset0D.DataChannel(channel_db_name, self.db_connection if cnx is None else cnx)

    def get_all_channels(self):
        """
        return all channels for this node
        the return is a dict {channel_name:DataChannel}
        """
        return dict(((chan_name, self.get_channel(chan_name))
                     for chan_name in self._channels_name))

    def _get_db_names(self):
        db_names = DataNode._get_db_names(self)
        db_names.append(self._channels_name._name)
        db_names.extend(
            (channel._name for channel in self._channels.itervalues()))
        return db_names
