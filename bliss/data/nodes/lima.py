# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import struct
import math
import numpy
import typing
from bliss.common.tango import DeviceProxy
from bliss.data.nodes.channel import ChannelDataNodeBase
from bliss.data.events import EventData, LimaImageStatusEvent
from bliss.config.settings import QueueObjSetting
from silx.third_party.EdfFile import EdfFile


try:
    import h5py
except ImportError:
    h5py = None

VIDEO_HEADER_FORMAT = "!IHHqiiHHHH"
DATA_ARRAY_MAGIC = struct.unpack(">I", b"DTAY")[0]
HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)
VIDEO_MODES = {0: numpy.uint8, 1: numpy.uint16, 2: numpy.int32, 3: numpy.int64}
IMAGE_MODES = {
    0: numpy.uint8,
    1: numpy.uint16,
    2: numpy.uint32,
    4: numpy.int8,
    5: numpy.int16,
    6: numpy.int32,
}


UNSET = object()
"""Allow to discriminate None and unset value from function argument,
when None is a valid argument which can be used"""


class ImageFormatNotSupported(Exception):
    """"Raised when the RAW data from a Lima device can't be decoded as a grey
    scale or RGB numpy array."""


class Frame(typing.NamedTuple):
    """
    Provide data frame from Lima including few metadata
    """

    data: numpy.array
    """Data of the frame"""

    frame_number: typing.Optional[int]
    """Number of the frame. Can be None. 0 is the first frame"""

    source: str
    """Source of the data. Can be "video", "file", or "memory"
    """

    def __bool__(self) -> bool:
        """Return true is this frame is not None

        Helper for compatibility. This have to be removed. The API should return
        `None` when there is nothing, and not return an empty tuple.

        ..note:: 2020-02-27: This have to be removed at one point
        """
        return self.data is not None

    def __iter__(self):
        """Mimick a 2-tuple, for compatibility with the previous version.

        ..note:: 2020-02-27: This have to be removed at one point
        """
        yield self[0]
        yield self[1]


def read_video_last_image(proxy) -> typing.Optional[typing.Tuple[numpy.ndarray, int]]:
    """Read and decode video last image from a Lima detector

    Argument:
        proxy: A Tango Lima proxy

    Returns:
        A tuple with the frame data (as a numpy array), and the frame number
        if an image is available. None if there is not yet acquired image.

    Raises:
        ImageFormatNotSupported: when the retrieved data is not supported
    """
    # get last video image
    _, raw_data = proxy.video_last_image
    if len(raw_data) < HEADER_SIZE:
        raise ImageFormatNotSupported("Image header smaller than the expected size")

    (
        magic,
        header_version,
        image_mode,
        image_frame_number,
        image_width,
        image_height,
        endian,
        header_size,
        pad0,
        pad1,
    ) = struct.unpack(VIDEO_HEADER_FORMAT, raw_data[:HEADER_SIZE])

    if magic != 0x5644454f:
        raise ImageFormatNotSupported("Magic header not supported (found %s)." % magic)

    if header_version != 1:
        raise ImageFormatNotSupported(
            "Image header version not supported (found %s)." % header_version
        )
    if image_frame_number < 0:
        return None

    if endian != 0:
        raise ImageFormatNotSupported(
            "Decoding video frame from this Lima device is "
            "not supported by bliss cause of the endianness (found %s)." % endian
        )

    if pad0 != 0 or pad1 != 0:
        raise ImageFormatNotSupported(
            "Decoding video frame from this Lima device is not supported "
            "by bliss cause of the padding (found %s, %s)." % (pad0, pad1)
        )

    mode = VIDEO_MODES.get(image_mode)
    if mode is None:
        raise ImageFormatNotSupported(
            "Video format unsupported (found %s)." % image_mode
        )

    data = numpy.frombuffer(raw_data[header_size:], dtype=mode).copy()
    data.shape = image_height, image_width
    return data, image_frame_number


def read_image(proxy, image_nb: int) -> numpy.ndarray:
    """Read and decode image (or last image ready) from a Lima detector.

    Argument:
        proxy: A Tango Lima proxy
        image_nb: The image index to decode, else -1 to use the last index
            (last_image_ready).

    Returns:
        The frame data (as a numpy array)

    Raises:
        IndexError: when no images are yet taken
        ImageFormatNotSupported: when the retrieved data is not supported
    """
    if image_nb == -1:
        image_nb = proxy.last_image_ready
        if image_nb == -1:
            raise IndexError("No image has been taken yet")

    try:
        raw_msg = proxy.readImage(image_nb)
    except Exception:
        raise RuntimeError("Error while reading image")
    else:
        raw_msg = raw_msg[-1]

    struct_format = "<IHHIIHHHHHHHHHHHHHHHHHHIII"
    header_size = struct.calcsize(struct_format)
    values = struct.unpack(struct_format, raw_msg[:header_size])
    if values[0] != DATA_ARRAY_MAGIC:
        raise ImageFormatNotSupported("Not a Lima data")
    header_offset = values[2]

    format_id = values[4]
    data_format = IMAGE_MODES.get(format_id)
    if data_format is None:
        raise ImageFormatNotSupported(
            "Image format from Lima Tango device not supported (found %s)." % format_id
        )

    data = numpy.fromstring(raw_msg[header_offset:], dtype=data_format)
    data.shape = values[8], values[7]
    return data


class LimaDataView:
    def __init__(
        self,
        queue,
        queue_ref,
        from_index,
        to_index,
        last_image_ready=-1,
        from_stream=False,
    ):
        self._queue = queue
        self._queue_ref = queue_ref
        self.from_index = from_index
        self._to_index = to_index
        self.last_image_ready = last_image_ready
        self.from_stream = from_stream

    @property
    def to_index(self):
        self._update()
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

    @property
    def ref_status(self):
        events = self._queue.rev_range(count=1)
        if events:
            index, raw = events[0]
            ev = LimaImageStatusEvent(raw=raw)
        else:  # Lima acqusition has not yet started.
            ev = LimaImageStatusEvent({})
        return ev.status

    @property
    def all_ref_data(self):
        return self._queue_ref[0:]

    @property
    def first_ref_data(self):
        return self.all_ref_data[0]

    @property
    def current_lima_acq(self):
        """ return the current server acquisition number
        """
        lima_acq = self.connection.get(self.server_url)
        return int(lima_acq if lima_acq is not None else -1)

    def _get_proxy(self):
        try:
            proxy = DeviceProxy(self.server_url) if self.server_url else None
        except Exception:
            proxy = None
        return proxy

    def is_video_frame_have_meaning(self, update=True):
        """Returns True if the frame number reached from the header from
        the Lima video have a meaning in the full scan.

        Returns a boolean, else None if this information is not yet known.
        """
        if update:
            self._update()
        if self.acq_trigger_mode is None:
            return None
        # FIXME: This still can be wrong for a scan with many groups of MULTI images
        # The function is_video_frame_have_meaning itself have not meaning and
        # should be removed
        return self.acq_trigger_mode in [
            "EXTERNAL_TRIGGER_MULTI",
            "INTERNAL_TRIGGER_MULTI",
        ]

    def get_last_live_image(self, proxy=UNSET):
        """Returns the last image data from stream within it's frame number.

        If no data is available, the function returns tuple (None, None).

        If camera device is not configured with INTERNAL_TRIGGER_MULTI, and
        then the reached frame number have no meaning, a None is returned.
        """
        self._update()

        if proxy is UNSET:
            proxy = self._get_proxy()

        if not proxy:
            # FIXME: It should return None
            return Frame(None, None, None)

        if not self.from_stream:
            # FIXME: It should return None
            return Frame(None, None, None)

        result = read_video_last_image(proxy)
        if result is None:
            # FIXME: It should return None
            return Frame(None, None, None)

        frame, frame_number = result
        if not self.is_video_frame_have_meaning(update=False):
            # In this case the reached frame have no meaning within the full
            # scan. It is better not to provide it
            frame_number = None
        return Frame(frame, frame_number, "video")

    def get_last_image(self, proxy=UNSET):
        """Returns the last image from the received one, together with the frame id.

        :param proxy: lima server proxy
        :returns Frame:
        """
        self._update()

        if self.last_image_ready < 0:
            raise IndexError("No image has been taken yet")

        if proxy is UNSET:
            proxy = self._get_proxy()

        data = None
        if proxy:
            # Update to use the latest image
            self._update()
            frame_number = self.last_image_ready
            data = self._get_from_server_memory(proxy, frame_number)
            source = "memory"

        if data is None:
            # Update to use the latest image
            self._update()
            frame_number = self.last_image_ready
            data = self._get_from_file(frame_number)
            source = "file"

        return Frame(data, frame_number, source)

    def get_image(self, image_nb, proxy=UNSET):
        """
        :param int image_nb:
        :param proxy: lima server proxy
        :returns numpy.ndarray:
        """
        if image_nb < 0:
            raise ValueError("image_nb cannot be a negative number")
        self._update()
        if proxy is UNSET:
            proxy = self._get_proxy()
        data = None
        if proxy:
            data = self._get_from_server_memory(proxy, image_nb)
        if data is None:
            data = self._get_from_file(image_nb)
        return data

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            proxy = self._get_proxy()
            start, stop, step = idx.indices(len(self))
            start += self.from_index
            stop += self.from_index
            return numpy.asarray(
                list(self._image_range(start, stop, step, proxy=proxy))
            )
        elif isinstance(idx, list):
            proxy = self._get_proxy()
            idx = numpy.asarray(idx)
            if isinstance(idx[0].item(), bool):
                idx = numpy.nonzero(idx)
            idx += self.from_index
            return numpy.asarray(list(self._image_iter(idx, proxy=proxy)))
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
        proxy = self._get_proxy()
        yield from self._image_range(self.from_index, self.to_index + 1, proxy=proxy)

    def _image_range(self, start, stop, step=1, proxy=UNSET):
        yield from self._image_iter(range(start, stop, step), proxy=proxy)

    def _image_iter(self, image_nb_iterator, proxy=UNSET):
        if proxy is UNSET:
            proxy = self._get_proxy()
        for image_nb in image_nb_iterator:
            try:
                img = self.get_image(image_nb, proxy=proxy)
                if img is None:
                    break
                yield img
            except Exception:
                break

    def as_array(self):
        if len(self) == 1:
            # To be consistant with ChannelDataNode
            return list(self)[0]
        else:
            return numpy.asarray(self)

    def __len__(self):
        length = self.to_index - self.from_index + 1
        return 0 if length < 0 else length

    def _update(self):
        """Set LimadataView attributes from ref_status and the first ref_data
        """
        ref_status = self.ref_status
        for key, value in ref_status.items():
            setattr(self, key, value)
        try:
            ref_data = self.first_ref_data
        except IndexError:
            pass
        else:
            for key in ("acq_trigger_mode",):
                setattr(self, key, ref_data.get(key, None))

    def get_filenames(self):
        """All saved image filenames
        """
        self._update()
        return self._get_filenames(
            self.first_ref_data, *range(0, self.last_image_saved + 1)
        )

    def _get_filenames(self, ref_data, *image_nbs):
        """Specific image filenames
        """
        return LimaImageStatusEvent.image_filenames(
            ref_data, image_nbs=image_nbs, last_image_saved=self.last_image_saved
        )

    def _get_from_server_memory(self, proxy, image_nb):
        """
        :param proxy: lima server proxy
        :param int image_nb:
        :returns numpy.ndarray or None:
        """
        if self.current_lima_acq == self.lima_acq_nb:  # current acquisition is this one
            if self.last_image_ready < 0:
                raise IndexError("No image has been taken yet")
            if self.last_image_ready < image_nb:  # image not yet available
                raise IndexError("Image is not available yet")
            # should be in memory
            if self.buffer_max_number > (self.last_image_ready - image_nb):
                try:
                    return read_image(proxy, image_nb)
                except RuntimeError:
                    # As it's asynchronous, image seems to be no
                    # more available so read it from file
                    return None
            return None

    def _get_from_file(self, image_nb):
        """
        :param int image_nb:
        :returns numpy.ndarray or None:
        """
        try:
            ref_data = self.first_ref_data
        except IndexError:
            raise IndexError("Cannot retrieve image %d from file" % image_nb)
        values = self._get_filenames(ref_data, image_nb)
        filename, path_in_file, image_index, file_format = values[0]
        file_format = file_format.lower()
        if file_format.startswith("edf"):
            if file_format == "edfconcat":
                image_index = 0
            if EdfFile is not None:
                f = EdfFile(filename)
                return f.GetData(image_index)
            else:
                raise RuntimeError(
                    "EdfFile module is not available, " "cannot return image data."
                )
        elif file_format.startswith("hdf5"):
            if h5py is not None:
                with h5py.File(filename, mode="r") as f:
                    dataset = f[path_in_file]
                    return dataset[image_index]
        else:
            raise RuntimeError("Format not managed yet")


class LimaImageChannelDataNode(ChannelDataNodeBase):
    _NODE_TYPE = "lima"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO: ending with _data would give a problem?
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
            description = ev.status
            first_index = self._stream_image_count
            data = ev.get_data(self.first_ref_data, first_index)
            self._stream_image_count += len(data)
        return EventData(first_index=first_index, data=data, description=description)

    @property
    def all_ref_data(self):
        """All reference dicts

        :returns list(dict):
        """
        return self._queue_ref[0:]

    @property
    def first_ref_data(self):
        """The first reference data

        :returns dict:
        :raise IndexError: no reference data yet
        """
        return self.all_ref_data[0]

    @property
    def images_per_file(self):
        return self.first_ref_data.get("saving_frame_per_file")

    def get_file_references(self):
        """
        Retrieve all files references for this data set
        """
        # take the last in list because it's should be the final
        final_ref_data = self._queue_ref[-1]
        # in that case only one reference will be returned
        overwrite_policy = final_ref_data["overwritePolicy"].lower()
        if overwrite_policy == "multiset":
            last_file_number = final_ref_data["nextNumber"] + 1
        else:
            nb_files = int(
                math.ceil(
                    float(final_ref_data["acqNbFrames"])
                    / final_ref_data["framesPerFile"]
                )
            )
            last_file_number = final_ref_data["nextNumber"] + nb_files

        path_format = "%s%s%s%s" % (
            final_ref_data["directory"],
            final_ref_data["prefix"],
            final_ref_data["indexFormat"],
            final_ref_data["suffix"],
        )
        references = []
        file_format = final_ref_data["fileFormat"].lower()
        for next_number in range(final_ref_data["nextNumber"], last_file_number):
            full_path = path_format % next_number
            if file_format.startswith("hdf5"):
                # @todo see what's is needed for hdf5 dataset link
                pass
            references.append(full_path)
        return references

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append(self.db_name + "_data_ref")
        events = self._queue.range(count=1)
        if events:
            index, raw = events[0]
            ev = LimaImageStatusEvent(raw=raw)
            url = ev.status.get("server_url")
            if url:
                db_names.append(url)
        return db_names

    def __len__(self):
        return len(self.get(0, -1))
