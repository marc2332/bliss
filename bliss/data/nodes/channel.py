# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import functools
from bliss.data.node import DataNode
from bliss.data.events import EventData, ChannelDataEvent


# Default length of published channels
CHANNEL_MAX_LEN = 2048


class _ChannelDataNodeBase(DataNode):
    _NODE_TYPE = NotImplemented

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)
        self._queue = self._create_stream("data", maxlen=CHANNEL_MAX_LEN)
        self._last_index = self._idx_to_streamid(0)

    @classmethod
    def _idx_to_streamid(cls, idx):
        """Get the Redis stream ID from the sequence index

        :param int idx:
        :returns int:
        """
        # Redis can't has a stream ID 0
        return idx + 1

    @classmethod
    def _streamid_to_idx(cls, streamID):
        """
        :param bytes streamID:
        :returns int:
        """
        return super()._streamid_to_idx(streamID) - 1

    def _init_info(self, **kwargs):
        # This is a hack, just for self._create_struct. The name of this
        # DataNode (which is used to create the db_name) will replaced
        # by the channel name after composing the db_name.
        self.__channel_name = kwargs.get("channel_name", None)

        # Take specific arguments to populate `info`
        shape = kwargs.get("shape", None)
        dtype = kwargs.get("dtype", None)
        unit = kwargs.get("unit", None)
        fullname = kwargs.get("fullname", None)
        info = kwargs.get("info", {})
        if kwargs.get("create", False):
            if shape is not None:
                info["shape"] = shape
            if dtype is not None:
                info["dtype"] = dtype
            info["fullname"] = fullname
            info["unit"] = unit
        return info

    def _subscribe_stream(self, stream_suffix, reader, first_index=None, **kw):
        """Subscribe to a particular stream associated with this node.

        :param str stream_suffix: stream to add is "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        :param str or int first_index: Redis stream index (None is now)
        """
        if stream_suffix == "data":
            # This stream has position indexing, not time indexing.
            # No limit on the start index, so start from 0.
            first_index = 0
        super()._subscribe_stream(stream_suffix, reader, first_index=first_index, **kw)

    def _subscribe_all_streams(self, reader, yield_events=False, **kw):
        """Subscribe to all associated streams of this node.

        :param DataStreamReader reader:
        :param bool yield_events: yield Event or DataNode
        :param **kw: see DataNode
        """
        super()._subscribe_all_streams(reader, yield_events=yield_events, **kw)
        if yield_events:
            self._subscribe_stream(
                "data", reader, first_index=0, create=True, ignore_excluded=True
            )

    def __getitem__(self, idx):
        """
        :param int or slice idx: supports only slices with stride +1
        """
        if isinstance(idx, slice):
            if idx.step not in (1, None):
                raise IndexError("Stride not supported")
            n = len(self)

            if idx.start is None:
                from_index = 0
            else:
                from_index = idx.start
                if from_index < 0:
                    from_index += n

            if idx.stop is None:
                to_index = n
            else:
                to_index = idx.stop
                if to_index < 0:
                    to_index += n

            if from_index > to_index:
                raise IndexError("Reverse order not supported")
            elif from_index == to_index:
                return numpy.array([])
            to_index -= 1
        elif idx is Ellipsis:
            from_index = 0
            to_index = -1
        else:
            try:
                idx = int(idx)
            except Exception as e:
                raise IndexError from e
            if idx < 0:
                from_index = idx + len(self)
            else:
                from_index = idx
            to_index = None
        ret = self.get(from_index, to_index)
        if to_index is None:
            try:
                if not ret:
                    raise IndexError("index out of range")
            except ValueError:
                # non-empty numpy.ndarray
                pass
        return ret

    @property
    def shape(self):
        return self.info.get("shape")

    @property
    def dtype(self):
        return self.info.get("dtype")

    @property
    def fullname(self):
        """Same as AcquisitionChannel.fullname
        """
        return self.info.get("fullname")

    @property
    def short_name(self):
        """Same as AcquisitionChannel.short_name
        """
        _, _, last_part = self.name.rpartition(":")
        return last_part

    def _create_struct(self, db_name, short_name, node_type):
        # AcquisitionChannel.short_name is used for `self.db_name`.
        # AcquisitionChannel.fullname is used for `node.name`.
        name = self.__channel_name
        if not name:
            name = short_name
        return super()._create_struct(db_name, name, node_type)

    @property
    def unit(self):
        return self.info.get("unit")

    def get_db_names(self, **kw):
        db_names = super().get_db_names(**kw)
        db_names.append(self.db_name + "_data")
        return db_names

    def get_settings(self):
        return super().get_settings() + [self._queue]

    def store(self, event_dict, cnx=None):
        """Publish channel data in Redis
        """
        raise NotImplementedError

    def get(self, from_index, to_index=None):
        """Returns an item or a slice.

        :param int from_index: >= 0 (item at this index)
                               < 0  (last item (to_index is None), first item (to_index is not None))
                               None (first item)
        :param int to_index: >= 0 (get slice until and including this index),
                             < 0 (get slice until the end)
                             None (get item at index from_index)
        :returns numpy.ndarray, list, scalar, None or callable:
        :raises IndexError: out of range when slicing and
                              from_index>0 and to_index<0
                              to_index>0
                            otherwise returns None or []
        """
        raise NotImplementedError

    def get_as_array(self, from_index, to_index=None):
        """Like `get` but ensures the result is a numpy array.
        """
        return numpy.asarray(self.get(from_index, to_index), self.dtype)

    def decode_raw_events(self, events):
        """Decode raw stream data

        :param list((index, raw)) events:
        :returns EventData:
        """
        raise NotImplementedError


class ChannelDataNode(_ChannelDataNodeBase):
    _NODE_TYPE = "channel"

    def store(self, event_dict, cnx=None):
        """Publish channel data in Redis
        """
        ev = ChannelDataEvent(event_dict.get("data"), event_dict["description"])
        self._queue.add_event(ev, id=self._last_index, cnx=cnx)
        self._last_index += ev.npoints

    def get(self, from_index, to_index=None):
        """Returns an item or a slice.

        :param int from_index:
        :param int to_index:
        :returns numpy.ndarray, list, scalar, None or callable: only a list when no data
        """
        if from_index is None:
            from_index = 0
        if to_index is None:
            return self._get_item(from_index)
        else:
            from_index = max(from_index, 0)
            return self._get_slice(from_index, to_index)

    def _get_item(self, index):
        """Get data from a single point (None when the index does not exist).

        :param int index:  < 0: last item
                          >= 0: item at this index
        :returns scalar, None or callable: None instead of IndexError
        """
        if index < 0:
            events = self._queue.rev_range(count=1, cnx=self.db_connection)
        else:
            redis_index = self._idx_to_streamid(index)
            events = self._queue_range(redis_index, redis_index)
        return self._get_return(self._event_to_data, events, index)

    def _get_slice(self, from_index, to_index):
        """Get a data slice.

        :param int from_index: positive integer
        :param int to_index:    < 0: till the end
                               >= 0: until and including this index
        :returns numpy.ndarray, list, scalar or callable: a list when no data
        """
        if to_index < 0:
            redis_to_index = "+"  # means stream end
        else:
            redis_to_index = self._idx_to_streamid(to_index)
        redis_from_index = self._idx_to_streamid(from_index)
        events = self._queue_range(redis_from_index, redis_to_index)
        return self._get_return(self._events_to_data, events, from_index, to_index)

    def _get_return(self, events_to_data, events, *args):
        """
        :param callable or Any events_to_data:
        """
        if isinstance(events, list):
            return events_to_data(*args, events)
        else:
            # pipeline case: should return the conversion function
            return functools.partial(events_to_data, *args)

    def _queue_range(self, from_index, to_index):
        """The result includes `from_index` and `to_index` but
        can be larger on both sides due to the block size.

        :param int from_index:
        :param int or str to_index:
        :returns list(2-tuple) or callable:
        :raises RuntimeError: when using a Redis pipeline to
                              get partial queue events
        """
        if from_index in [0, 1] and to_index == "+":
            return self._queue.range(from_index, to_index, cnx=self.db_connection)
        org_from_index = from_index
        blocksize = 0
        result = []
        while True:
            from_index = max(from_index - blocksize, 0)
            events = self._queue.range(from_index, to_index, cnx=self.db_connection)
            if not isinstance(events, list):
                raise RuntimeError(
                    "Redis pipelines can only be used when retrieving the full queue range."
                )
            if events:
                result = events + result
                idx, raw = events[0]
                first_index = self._idx_to_streamid(self._streamid_to_idx(idx))
                if first_index <= org_from_index or from_index == 0:
                    break
                to_index = first_index - 1
                from_index = first_index
                blocksize = ChannelDataEvent.decode_npoints(raw)
            elif from_index == 0:
                break
            blocksize = max(blocksize, 1)
        return result

    def _events_to_data(self, from_index, to_index, events, single=False):
        """
        :param int from_index:
        :param int to_index:
        :param list((index, raw)) events:
        :param bool single: requested a single value, not a slice
        :returns numpy.ndarray or list: only a list when no data
        """
        event_data = self.decode_raw_events(events)
        data = event_data.data
        ndata = len(data)
        first_index = event_data.first_index

        # The last index is ALWAYS allowed to be higher than the available data
        # The first index is SOMETIMES allowed to be lower than the available data
        allow_lower = (to_index < 0 and from_index == 0) or single
        is_lower = from_index < first_index or first_index < 0
        if is_lower and not allow_lower:
            raise IndexError(
                "Data is not anymore available first_index:"
                f"{first_index} request_index:{from_index}"
            )

        # Data can be larger on both sides (see _queue_range)
        start = max(from_index - first_index, 0)
        if to_index < 0:
            stop = ndata
        else:
            nrequested = to_index - from_index + 1
            stop = min(start + nrequested, ndata)
        if stop - start == ndata:
            return data
        else:
            return data[start:stop]

    def _event_to_data(self, index, events):
        """
        :param int index:
        :param list((index, raw)) events:
        :returns scalar or None:
        """
        data = self._events_to_data(index, index, events, single=True)
        try:
            return data[-1]
        except IndexError:
            return None

    def decode_raw_events(self, events):
        """Decode and concatenate raw stream data

        :param list((index, raw)) events:
        :returns EventData:
        """
        data = list()
        first_index = -1
        description = None
        block_size = 0
        if events:
            first_index = self._streamid_to_idx(events[0][0])
            ev = ChannelDataEvent.merge(events)
            data = ev.array
            description = ev.description
            block_size = ev.npoints
        return EventData(
            first_index=first_index,
            data=data,
            description=description,
            block_size=block_size,
        )

    def __len__(self):
        events = self._queue.rev_range(count=1)
        if events:
            evdata = self.decode_raw_events(events)
            return evdata.first_index + evdata.block_size
        else:
            return 0
