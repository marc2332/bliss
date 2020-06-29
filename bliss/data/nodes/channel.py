# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.node import DataNode
from bliss.data.events import EventData
from bliss.config import streaming_events
import numpy
import pickle

# Default length of published channels
CHANNEL_MAX_LEN = 2048


def as_array(sequence, dtype):
    """Convert a sequence of sequences to a numpy array.
    Pad with NaN's when sequences have unequal size.

    :param Sequence sequence:
    :param dtype:
    :returns numpy.ndarray:
    """
    try:
        return numpy.asarray(sequence, dtype=dtype)
    except ValueError:
        # Sequences have unequal length
        shape = (len(sequence), numpy.max([len(x) for x in sequence]))
        arr = numpy.full(shape, numpy.nan, dtype=dtype)
        for src, dest in zip(sequence, arr):
            dest[: len(src)] = src
        return arr


class ChannelDataEvent(streaming_events.StreamEvent):
    TYPE = b"CHANNELDATA"
    DATA_KEY = b"__DATA__"
    DESC_KEY = b"__DESC__"
    NPOINTS_KEY = b"__NPOINTS__"

    def init(self, data, description):
        """
        :param Any data:
        :param dict description:
        """
        self.description = description
        self.data = data

    @property
    def shape(self):
        return self.description["shape"]

    @property
    def ndim(self):
        return len(self.shape)

    @property
    def dtype(self):
        return self.description["dtype"]

    @property
    def data(self):
        """Sequence of items when npoints>1, else an item.
        An item can be itself a sequence.
        """
        return self._data

    @property
    def npoints(self):
        return self._npoints

    @data.setter
    def data(self, value):
        if isinstance(value, numpy.ndarray):
            if self.ndim == value.ndim:
                # Only one data point provided
                npoints = 1
            else:
                # Each element is a new data point
                npoints = len(value)
                if npoints == 1:
                    value = value[0]
        elif isinstance(value, (list, tuple)):
            # Each element is a new data point
            npoints = len(value)
            value = numpy.array(value, dtype=self.dtype)
            if npoints == 1:
                value = value[0]
        else:
            # Only one data point provided
            npoints = 1
        self._data = value
        self._npoints = npoints

    def _encode(self):
        raw = super()._encode()
        raw[self.DESC_KEY] = self.generic_encode(self.description)
        raw[self.NPOINTS_KEY] = self.encode_integral(self._npoints)
        raw[self.DATA_KEY] = self.generic_encode(self._data)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.description = self.generic_decode(raw[self.DESC_KEY])
        self._npoints = self.decode_integral(raw[self.NPOINTS_KEY])
        self._data = self.generic_decode(raw[self.DATA_KEY])


class ChannelDataNode(DataNode):
    _NODE_TYPE = "channel"

    def __init__(self, name, **keys):
        shape = keys.pop("shape", None)
        dtype = keys.pop("dtype", None)
        unit = keys.pop("unit", None)
        fullname = keys.pop("fullname", None)
        info = keys.pop("info", dict())
        if keys.get("create", False):
            if shape is not None:
                info["shape"] = shape
            if dtype is not None:
                info["dtype"] = dtype
            info["fullname"] = fullname
            info["unit"] = unit

        DataNode.__init__(self, self._NODE_TYPE, name, info=info, **keys)

        self._queue = self.create_associated_stream("data", maxlen=CHANNEL_MAX_LEN)
        self._last_index = 1  # redis can't starts at 0

    def _create_struct(self, db_name, name, node_type):
        # fix the channel name
        fullname = self._info["fullname"]
        if fullname:
            if fullname.endswith(f":{name}"):
                # no alias, name must be fullname
                name = fullname
            elif fullname.startswith("axis:"):
                name = f"axis:{name}"
        return super()._create_struct(db_name, name, node_type)

    def store(self, event_dict, cnx=None):
        """Publish channel data in Redis
        """
        ev = ChannelDataEvent(event_dict.get("data"), event_dict["description"])
        self._queue.add_event(ev, id=self._last_index, cnx=cnx)
        self._last_index += ev.npoints

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            if idx.step not in (1, None):
                raise ValueError("Stride not supported")

            if idx.start is None:
                from_index = 0
            else:
                from_index = idx.start
            if from_index < 0:
                from_index += len(self)

            if idx.stop is None:
                to_index = -1
            else:
                to_index = idx.stop - 1
            if to_index < 0:
                to_index += len(self)

            if from_index > to_index:
                return []
        elif idx is Ellipsis:
            from_index = 0
            to_index = -1
        else:
            if idx < 0:
                from_index = idx + len(self)
            else:
                from_index = idx
            to_index = None
        return self.get(from_index, to_index)

    def get(self, from_index, to_index=None):
        """Returns and item or a slice.

        :param int from_index: positive integer
        :param int or None to_index: positive integer (get slice until and including this index),
                                     None (get item at index from_index)
                                     -1 (get slice until the end)
        :returns numpy.ndarray, list, scalar, None or callable: only a list when no data
        """
        if from_index is None:
            from_index = 0
        if to_index is None:
            return self.get_item(from_index)
        else:
            return self.get_slice(from_index, to_index)

    def get_item(self, index):
        """Get data from a single point (None when the index does not exist).

        :param int index:
        :returns numpy.ndarray, scalar or None:
        """
        if index < 0:
            events = self._queue.rev_range(count=1)
        else:
            redis_index = index + 1  # redis starts at 1
            events = self._queue_range(redis_index, redis_index)
        data = self.events_to_data(index, index, events)
        try:
            return data[-1]
        except IndexError:
            return None

    def get_slice(self, start, stop):
        """Get a data slice (my be shorter or empty than requested).

        :param int start:
        :param int stop:
        :returns numpy.ndarray, list, scalar or callable: only a list when no data
        """
        if stop < 0:
            redis_stop = "+"  # means stream end
        else:
            redis_stop = stop + 1  # redis starts at 1
        redis_start = start + 1  # redis starts at 1
        events = self._queue_range(redis_start, redis_stop)
        if isinstance(events, list):
            return self.events_to_data(start, stop, events)
        else:
            # pipeline case from get_data
            # should return the conversion function
            def events_to_data(events):
                return self.events_to_data(start, stop, events)

            return events_to_data

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
                ev = ChannelDataEvent(raw=raw)
                first_index = int(idx.split(b"-")[0])
                if first_index <= org_from_index or from_index == 0:
                    break
                to_index = first_index - 1
                from_index = first_index
                blocksize = ev.npoints
            elif from_index == 0:
                break
            blocksize = max(blocksize, 1)
        return result

    def events_to_data(self, from_index, to_index, events):
        """
        :param list((index, raw)) events:
        :returns numpy.ndarray or list: only a list when no data
        """
        event_data = self.decode_raw_events(events)
        first_index = event_data.first_index
        if first_index < 0:
            return []
        if first_index > from_index and from_index > 0:
            raise RuntimeError(
                "Data is not anymore available first_index:"
                f"{first_index} request_index:{from_index}"
            )
        data = event_data.data
        # Data can be larger on both sides (see _queue_range)
        start = max(from_index - first_index, 0)
        ndata = len(data)
        if to_index < 0:
            stop = ndata
        else:
            stop = start + to_index - from_index + 1
        if stop - start == ndata:
            return data
        else:
            return data[start:stop]

    def decode_raw_events(self, events):
        """Decode and concatenate raw stream data

        :param list((index, raw)) events:
        :returns EventData:
        """
        data = list()
        descriptions = list()
        first_index = -1
        dtype = None
        npoints = 0
        for i, (index, raw) in enumerate(events):
            ev = ChannelDataEvent(raw=raw)
            if i == 0:
                first_index = int(index.split(b"-")[0]) - 1
                dtype = ev.dtype
                npoints = ev.npoints
            if ev.npoints == 1:
                data.append(ev.data)
            else:
                data.extend(ev.data)
            descriptions.append(ev.description)
        data = as_array(data, dtype)
        return EventData(
            first_index=first_index,
            data=data,
            description=descriptions,
            block_size=npoints,
        )

    def get_as_array(self, from_index, to_index=None):
        """Like `get` but ensures the result is a numpy array.
        """
        # This is just because `get` returns [] when no elements
        return numpy.asarray(self.get(from_index, to_index), self.dtype)

    def __len__(self):
        # fetching last event
        # using last index as old queue-len
        events = self._queue.rev_range(count=1)
        if not events:
            return 0
        first_index, raw = events[0]
        ev = ChannelDataEvent(raw=raw)
        first_index = int(first_index.split(b"-")[0]) - 1
        return first_index + ev.npoints

    @property
    def shape(self):
        return self.info.get("shape")

    @property
    def dtype(self):
        return self.info.get("dtype")

    @property
    def fullname(self):
        return self.info.get("fullname")

    @property
    def short_name(self):
        _, _, short_name = self.name.rpartition(":")
        return short_name

    @property
    def unit(self):
        return self.info.get("unit")

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append(self.db_name + "_data")
        return db_names
