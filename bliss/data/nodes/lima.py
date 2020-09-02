# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import math
import numpy
import warnings
from bliss.data.nodes.channel import ChannelDataNodeBase
from bliss.data.events import EventData, LimaImageStatusEvent
from bliss.config.settings import QueueObjSetting
from bliss.data import lima_image


class LimaDataView:
    def __init__(self, queue, queue_ref, from_index, to_index, from_stream=False):
        """
        :param DataStream queue: acquisition status events
        :param QueueObjSetting queue_ref: acquisition info
        :param int from_index:
        :param int to_index: when <0 we will take the last image
                             that is "ready" which may change after `update`
        :param bool from_stream:
        """
        self._queue = queue
        self._queue_ref = queue_ref
        self.from_index = from_index
        self._to_index = to_index
        self.from_stream = from_stream
        self._status_event = None

    def __getattr__(self, attr):
        # Get attribute from the status event
        try:
            return getattr(self.status_event, attr)
        except AttributeError:
            raise AttributeError(attr)

    @property
    def to_index(self):
        """Either a fixed number or the last image that is "ready"
        """
        self.update()
        last_index = self.last_image_ready
        if self._to_index >= 0:
            return min(self._to_index, last_index)
        else:
            return last_index

    @property
    def last_index(self):
        """WARNING: this is the last image index + 1
        """
        return self.to_index + 1

    @property
    def connection(self):
        return self._queue._cnx()

    def update(self):
        """Get the latest status event from the data stream
        and add the first element of the reference settings.
        It is safe to call this as much as you want.
        """
        events = self._queue.rev_range(count=1)
        if events:
            index, raw = events[0]
            ev = LimaImageStatusEvent(raw=raw)
        else:  # Lima acqusition has not yet started.
            ev = LimaImageStatusEvent({})
        try:
            ev.info = self.first_ref_data
        except IndexError:
            pass
        ev.connection = self.connection
        self._status_event = ev

    @property
    def status_event(self):
        if self._status_event is None:
            self.update()
        return self._status_event

    @property
    def ref_status(self):
        warnings.warn(
            "ref_status is deprecated. Use 'status_event.status' instead.",
            FutureWarning,
        )
        return self.status_event.status

    @property
    def all_ref_data(self):
        """
        :returns list(dict):
        """
        return self._queue_ref[0:]

    @property
    def first_ref_data(self):
        """
        :returns dict:
        """
        return self._queue_ref[0]

    def is_video_frame_have_meaning(self):
        """Returns True if the frame number reached from the header from
        the Lima video have a meaning in the full scan.

        Returns a boolean, else None if this information is not yet known.
        """
        self.update()
        return self.status_event.is_video_frame_have_meaning()

    def get_last_live_image(self):
        """Returns the last image data from stream within it's frame number.

        If no data is available, the function returns tuple (None, None).

        If camera device is not configured with INTERNAL_TRIGGER_MULTI, and
        then the reached frame number have no meaning, a None is returned.

        :returns Frame:
        """
        if not self.from_stream:
            # FIXME: It should return None
            return lima_image.Frame(None, None, None)
        self.update()
        return self.status_event.get_last_live_image()

    def get_last_image(self):
        """Returns the last image from the received one, together with the frame id.

        :returns Frame:
        """
        self.update()
        return self.status_event.get_last_image()

    def get_image(self, image_nb):
        """
        :param int image_nb:
        :returns numpy.ndarray:
        """
        if image_nb < 0:
            raise ValueError("image_nb cannot be a negative number")
        self.update()
        return self.status_event.get_image(image_nb)

    def __getitem__(self, idx):
        """Get images from server or file
        """
        if isinstance(idx, slice):
            start, stop, step = idx.indices(len(self))
            start += self.from_index
            stop += self.from_index
            return numpy.asarray(list(self._image_range(start, stop, step)))
        elif isinstance(idx, list):
            idx = numpy.asarray(idx)
            if isinstance(idx[0].item(), bool):
                idx = numpy.nonzero(idx)
            idx += self.from_index
            return numpy.asarray(list(self._image_iter(idx)))
        elif isinstance(idx, tuple):
            # This would slice the image dimensions
            raise NotImplementedError
        else:
            try:
                idx = int(idx)
            except Exception as e:
                raise IndexError from e
            if self.from_stream and idx == -1:
                img = self.get_image(-1)
            else:
                if idx < 0:
                    index = self.to_index + 1 + idx
                    if index < 0:
                        raise IndexError("No image available")
                else:
                    index = self.from_index + idx
                img = self.get_image(index)
            if img is None:
                raise IndexError
            return img

    def __iter__(self):
        """Iterator over images from server or file
        """
        yield from self._image_range(self.from_index, self.to_index + 1)

    def _image_range(self, start, stop, step=1):
        """Iterator over images from server or file
        """
        yield from self._image_iter(range(start, stop, step))

    def _image_iter(self, image_nb_iterator):
        """Iterator over images from server or file
        """
        for image_nb in image_nb_iterator:
            try:
                img = self.get_image(image_nb)
            except IndexError:
                img = None
            if img is None:
                break
            yield img

    def as_array(self):
        if len(self) == 1:
            # To be consistant with ChannelDataNode
            return list(self)[0]
        else:
            return numpy.asarray(self)

    def __len__(self):
        length = self.to_index - self.from_index + 1
        return 0 if length < 0 else length

    def all_image_references(self, saved=False):
        """Get the image references.

        :param bool saved: ready or ready and saved
        :returns list(tuple): file name, path-in-file, image index, file format
                              File format (HDF5, HDF5BS, EDFLZ4, ...) is not file extension!
        :raise RuntimeError: images will never be saved
        """
        self.update()
        return self.status_event.all_image_references(saved=saved)

    def image_references(self, image_nbs, saved=False):
        """Get the image references.

        :param sequence image_nbs:
        :param bool saved: ready or ready and saved
        :returns list(tuple): file name, path-in-file, image index, file format
                              File format (HDF5, HDF5BS, EDFLZ4, ...) is not file extension!
        :raise RuntimeError: some images are not ready or saved yet
                             or images will never be saved
        """
        self.update()
        return self.status_event.image_references(image_nbs, saved=saved)

    def image_reference(self, image_nb, saved=False):
        """Get the image references.

        :param int image_nb:
        :param bool saved: ready or ready and saved
        :returns tuple: file name, path-in-file, image index, file format
                        File format (HDF5, HDF5BS, EDFLZ4, ...) is not file extension!
        :raise RuntimeError: image is not ready or saved yet
                             or images will never be saved
        """
        self.update()
        return self.status_event.image_reference(image_nb, saved=saved)

    def iter_image_references(self, image_nbs=None, saved=False):
        """Get the image references.

        Stops iterating when it encounters an image that is not
        ready or saved yet, regardless of how many images you
        asked for.

        :param sequence image_nbs:
        :param bool saved: ready or ready and saved
        :yields list(tuple): file name, path-in-file, image index, file format
                             File format (HDF5, HDF5BS, EDFLZ4, ...) is not file extension!
        :raises RuntimeError: images will never be saved
        """
        self.update()
        yield from self.status_event.iter_image_references(
            image_nbs=image_nbs, saved=saved
        )

    def get_filenames(self):
        warnings.warn(
            "'get_filenames' is deprecated. Use 'all_image_references' instead.",
            FutureWarning,
        )
        return self.all_image_references()

    def _get_filenames(self, ref_data, *image_nbs):
        warnings.warn(
            "'_get_filenames' is deprecated. Use 'image_references' itself.",
            FutureWarning,
        )
        return self.image_references(image_nbs)


class LimaImageChannelDataNode(ChannelDataNodeBase):
    _NODE_TYPE = "lima"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue_ref = QueueObjSetting(
            f"{self.db_name}_data_ref", connection=self.db_connection
        )
        self.from_stream = False
        self._local_ref_status = dict()
        self._stream_image_count = 0

    def store(self, event_dict, cnx=None):
        """Publish lima reference in Redis
        """
        data = event_dict["data"]
        if data.get("in_prepare", False):  # in prepare phase
            ref_data = event_dict["description"]
            self.info.update(ref_data)
            self._queue_ref.append(ref_data)
            self._local_ref_status = data
            self._local_ref_status["lima_acq_nb"] = self.db_connection.incr(
                data["server_url"]
            )
        else:  # during acquisition
            self._local_ref_status.update(data)
            ev = LimaImageStatusEvent(self._local_ref_status)
            self._queue.add_event(ev, id=self._last_index, cnx=cnx)
            self._last_index += 1

    def get(self, from_index, to_index=None):
        """
        Return a view on data references.

        **from_index** from which image index you want to get
        **to_index** to which index you want images
            if to_index is None => only one image which as index from_index
            if to_index < 0 => to the end of acquisition
        """
        return LimaDataView(
            self._queue,
            self._queue_ref,
            from_index,
            to_index if to_index is not None else from_index,
            from_stream=self.from_stream,
        )

    def get_as_array(self, from_index, to_index=None):
        """Like `get` but ensures the result is a numpy array.
        """
        return numpy.asarray(self.get(from_index, to_index).as_array(), self.dtype)

    def decode_raw_events(self, events):
        """Decode raw stream data and get image URI's.

        :param list((index, raw)) events:
        :returns EventData:
        """
        data = list()
        first_index = -1
        description = None
        if events:
            # The number of events is NOT equal to the number of images
            # The number of images can be derived from the event data though
            # TODO: first_index is only accurate if we use the same DataNode instance!!!
            ev = LimaImageStatusEvent.merge(events)
            ev.info = self.first_ref_data
            first_index = self._stream_image_count
            try:
                data = ev.image_reference_range(first_index)
            except RuntimeError:
                pass
            self._stream_image_count += len(data)
            description = ev.status
        return EventData(first_index=first_index, data=data, description=description)

    @property
    def all_ref_data(self):
        """
        :returns list(dict):
        """
        return self._queue_ref[0:]

    @property
    def first_ref_data(self):
        """
        :returns dict:
        """
        return self._queue_ref[0]

    @property
    def images_per_file(self):
        return self.first_ref_data.get("saving_frame_per_file")

    def get_db_names(self):
        db_names = super().get_db_names()
        db_names.append(self.db_name + "_data_ref")
        events = self._queue.range(count=1)
        if events:
            index, raw = events[0]
            ev = LimaImageStatusEvent(raw=raw)
            url = ev.server_url
            if url:
                db_names.append(url)
        return db_names

    def __len__(self):
        return len(self.get(0, -1))
