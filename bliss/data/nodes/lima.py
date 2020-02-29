# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import struct
import math
import pickle
import numpy
import typing
from bliss.common.tango import DeviceProxy
from bliss.data.node import DataNode
from bliss.data.events import EventData
from bliss.config.settings import QueueObjSetting
from bliss.config.streaming import DataStream
from silx.third_party.EdfFile import EdfFile

try:
    import h5py
except ImportError:
    h5py = None

VIDEO_HEADER_FORMAT = "!IHHqiiHHHH"
HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)

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


def image_filenames(ref_data, image_nbs, last_image_saved=None):
    """
    :param HashObjSetting ref_data:
    :param sequence image_nbs:
    :param int last_image_saved:
    :returns list(tuple): file name, path-in-file, image index, file format
                          File format is not file extension (HDF5, HDF5BS, EDFLZ4, ...)
    :raises RuntimeError: when an image is not saved already
    """
    saving_mode = ref_data.get("saving_mode", "MANUAL")
    if saving_mode == "MANUAL":  # files are not saved
        raise RuntimeError("Images were not saved")

    overwrite_policy = ref_data.get("saving_overwrite", "ABORT").lower()
    if overwrite_policy == "multiset":
        nb_image_per_file = ref_data["acq_nb_frames"]
    else:
        nb_image_per_file = ref_data.get("saving_frame_per_file", 1)

    first_file_number = ref_data.get("saving_next_number", 0)
    path_format = os.path.join(
        ref_data["saving_directory"],
        "%s%s%s"
        % (
            ref_data["saving_prefix"],
            ref_data.get("saving_index_format", "%04d"),
            ref_data["saving_suffix"],
        ),
    )
    returned_params = list()
    file_format = ref_data["saving_format"]
    if last_image_saved is None:
        last_image_saved = max(image_nbs)
    for image_nb in image_nbs:
        if image_nb > last_image_saved:
            raise RuntimeError("Image %d was not saved" % image_nb)

        image_index_in_file = image_nb % nb_image_per_file
        file_nb = first_file_number + image_nb // nb_image_per_file
        file_path = path_format % file_nb
        if file_format.lower().startswith("hdf5"):
            if ref_data.get("lima_version", "<1.9.1") == "<1.9.1":
                # 'old' lima
                path_in_file = (
                    "/entry_0000/instrument/"
                    + ref_data["user_detector_name"]
                    + "/data/array"
                )
            else:
                # 'new' lima
                path_in_file = (
                    f"/entry_0000/{ref_data['user_instrument_name']}"
                    + f"/{ref_data['user_detector_name']}/data"
                )
            returned_params.append(
                (file_path, path_in_file, image_index_in_file, file_format)
            )
        else:
            returned_params.append((file_path, "", image_index_in_file, file_format))
    return returned_params


class LimaImageChannelDataNode(DataNode):
    DATA = b"__data__"

    class LimaDataView(object):
        DataArrayMagic = struct.unpack(">I", b"DTAY")[0]

        IMAGE_MODES = {
            0: numpy.uint8,
            1: numpy.uint16,
            2: numpy.uint32,
            4: numpy.int8,
            5: numpy.int16,
            6: numpy.int32,
        }

        VIDEO_MODES = {0: numpy.uint8, 1: numpy.uint16, 2: numpy.int32, 3: numpy.int64}

        def __init__(self, data, data_ref, from_index, to_index, from_stream=False):
            self.data = data
            self.data_ref = data_ref
            self.from_index = from_index
            self.to_index = to_index
            self.last_image_ready = -1
            self.from_stream = from_stream

        @property
        def ref_status(self):
            raw_data = self.data.rev_range(count=1)
            if raw_data:
                index, raw_event = raw_data[0]
                return pickle.loads(raw_event[LimaImageChannelDataNode.DATA])
            else:  # Lima acqusition is not yet started.
                return {
                    "lima_acq_nb": -1,
                    "buffer_max_number": -1,
                    "last_image_acquired": -1,
                    "last_image_ready": -1,
                    "last_counter_ready": -1,
                    "last_image_saved": -1,
                }

        @property
        def ref_data(self):
            return self.data_ref[0:]

        @property
        def last_index(self):
            """ evaluate the last image index
            """
            self._update()
            if self.to_index >= 0:
                return self.to_index
            return self.last_image_ready + 1

        @property
        def current_lima_acq(self):
            """ return the current server acquisition number
            """
            cnx = self.data._cnx()
            lima_acq = cnx.get(self.server_url)
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

            # get last video image
            _, raw_data = proxy.video_last_image
            if len(raw_data) <= HEADER_SIZE:
                # FIXME: It should return None
                return Frame(None, None, None)

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

            if endian != 0:
                raise ImageFormatNotSupported(
                    "Decoding video frame from this Lima device is "
                    "not supported by bliss cause of the endianness (found %s)."
                    % endian
                )

            if pad0 != 0 or pad1 != 0:
                raise ImageFormatNotSupported(
                    "Decoding video frame from this Lima device is not supported "
                    "by bliss cause of the padding (found %s, %s)." % (pad0, pad1)
                )

            if magic != 0x5644454f:
                raise ImageFormatNotSupported(
                    "Magic header not supported (found %s)." % magic
                )

            if header_version != 1:
                raise ImageFormatNotSupported(
                    "Image header version not supported (found %s)." % header_version
                )
            if image_frame_number < 0:
                raise IndexError("Image (from Lima live interface) not available yet.")

            mode = self.VIDEO_MODES.get(image_mode)
            if mode is None:
                raise ImageFormatNotSupported(
                    "Video format unsupported (found %s)." % image_mode
                )

            data = numpy.frombuffer(raw_data[header_size:], dtype=mode).copy()
            data.shape = image_height, image_width

            if not self.is_video_frame_have_meaning(update=False):
                # In this case the reached frame have no meaning within the full
                # scan. It is better not to provide it
                image_frame_number = None
            return Frame(data, image_frame_number, "video")

        def get_last_image(self, proxy=UNSET):
            """Returns the last image from the received one, together with the frame id.
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
            if image_nb < 0:
                raise ValueError("image_nb must be a real image number")

            self._update()

            if proxy is UNSET:
                proxy = self._get_proxy()

            data = None
            if proxy:
                data = self._get_from_server_memory(proxy, image_nb)

            if data is None:
                return self._get_from_file(image_nb)
            else:
                return data

        def __getitem__(self, item_index):
            if isinstance(item_index, tuple):
                item_index = slice(*item_index)
            if isinstance(item_index, slice):
                proxy = self._get_proxy()
                return tuple(
                    (
                        self.get_image(self.from_index + image_nb, proxy=proxy)
                        for image_nb in item_index
                    )
                )
            else:
                if self.from_stream and item_index == -1:
                    return self.get_image(-1)
                if item_index < 0:
                    start = self.last_index
                    if start == 0:
                        raise IndexError("No image available")
                else:
                    start = self.from_index
                return self.get_image(start + item_index)

        def __iter__(self):
            proxy = self._get_proxy()
            for image_nb in range(self.from_index, self.last_index):
                yield self.get_image(image_nb, proxy=proxy)

        def __len__(self):
            length = self.last_index - self.from_index
            return 0 if length < 0 else length

        def _update(self):
            ref_status = self.ref_status
            for key in (
                "server_url",
                "lima_acq_nb",
                "buffer_max_number",
                "last_image_acquired",
                "last_image_ready",
                "last_counter_ready",
                "last_image_saved",
            ):
                if key in ref_status:
                    setattr(self, key, ref_status[key])
            if len(self.ref_data) >= 1:
                ref_data = self.ref_data[0]
                for key in ("acq_trigger_mode",):
                    if key in ref_data:
                        setattr(self, key, ref_data[key])

        def _get_from_server_memory(self, proxy, image_nb):
            if (
                self.current_lima_acq == self.lima_acq_nb
            ):  # current acquisition is this one
                if self.last_image_ready < 0:
                    raise IndexError("No image has been taken yet")
                if self.last_image_ready < image_nb:  # image not yet available
                    raise IndexError("Image is not available yet")
                # should be in memory
                if self.buffer_max_number > (self.last_image_ready - image_nb):
                    try:
                        raw_msg = proxy.readImage(image_nb)
                    except Exception:
                        # As it's asynchronous, image seems to be no
                        # more available so read it from file
                        return None
                    else:
                        return self._tango_unpack(raw_msg[-1])

        def get_filenames(self):
            """All saved image filenames
            """
            self._update()
            ref_data = self.ref_data[0]
            return self._get_filenames(ref_data, *range(0, self.last_image_saved + 1))

        def _get_filenames(self, ref_data, *image_nbs):
            """Specific image filenames
            """
            return image_filenames(
                ref_data, image_nbs=image_nbs, last_image_saved=self.last_image_saved
            )

        def _get_from_file(self, image_nb):
            for ref_data in self.ref_data:
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
                            "EdfFile module is not available, "
                            "cannot return image data."
                        )
                elif file_format.startswith("hdf5"):
                    if h5py is not None:
                        with h5py.File(filename, mode="r") as f:
                            dataset = f[path_in_file]
                            return dataset[image_index]
                else:
                    raise RuntimeError("Format not managed yet")

            raise IndexError("Cannot retrieve image %d from file" % image_nb)

        def _tango_unpack(self, msg):
            struct_format = "<IHHIIHHHHHHHHHHHHHHHHHHIII"
            header_size = struct.calcsize(struct_format)
            values = struct.unpack(struct_format, msg[:header_size])
            if values[0] != self.DataArrayMagic:
                raise RuntimeError("No Lima data")
            header_offset = values[2]

            format_id = values[4]
            data_format = self.IMAGE_MODES.get(format_id)
            if data_format is None:
                raise ImageFormatNotSupported(
                    "Image format from Lima Tango device not supported (found %s)."
                    % format_id
                )

            data = numpy.fromstring(msg[header_offset:], dtype=data_format)
            data.shape = values[8], values[7]
            return data

    def __init__(self, name, **keys):
        shape = keys.pop("shape", None)
        dtype = keys.pop("dtype", None)
        fullname = keys.pop("fullname", None)

        DataNode.__init__(self, "lima", name, **keys)

        if keys.get("create", False):
            self.info["shape"] = shape
            self.info["dtype"] = dtype
            self.info["fullname"] = fullname

        # why not trying to have LimaImageChannelDataNode deriving
        # from ChannelDataNode instead of DataNode ? This would
        # leave out the next lines, since it is already part of
        # ChannelDataNode:
        # fix the channel name
        if fullname and fullname.endswith(f":{name}"):
            # no alias, name must be fullname
            self._struct.name = fullname

        self.data = DataStream(
            "%s_data" % self.db_name, maxlen=1, connection=self.db_connection
        )
        self.data_ref = QueueObjSetting(
            f"{self.db_name}_data_ref", connection=self.db_connection
        )
        self.from_stream = False

        self._local_ref_status = dict()
        self._last_index = 1
        self._stream_image_count = 0

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

    def get(self, from_index, to_index=None):
        """
        Return a view on data references.

        **from_index** from which image index you want to get
        **to_index** to which index you want images
            if to_index is None => only one image which as index from_index
            if to_index < 0 => to the end of acquisition
        """
        return self.LimaDataView(
            self.data,
            self.data_ref,
            from_index,
            to_index if to_index is not None else from_index + 1,
            from_stream=self.from_stream,
        )

    @property
    def ref_data(self):
        return self.data_ref[0:]

    @property
    def images_per_file(self):
        return self.ref_data[0].get("saving_frame_per_file")

    def decode_raw_events(self, events):
        """
        transform internal Stream into data
        raw_datas -- should be the return of xread or xrange.
        """
        data = list()
        first_index = -1
        ref_status = None
        if events:
            # The number of events is NOT equal to  the number of images
            # The number of images can be derived from the event data though
            index, raw_data = events[-1]
            ref_status = pickle.loads(raw_data[self.DATA])
            first_index = self._stream_image_count
            # We can choose from:
            #   last_image_acquired
            #   last_image_ready (default for `LimaDataView.last_index`)
            #   last_counter_ready
            #   last_image_saved
            last_index = ref_status["last_image_ready"]
            if last_index >= first_index:
                # Data: filenames of new images since the last call to `decode_raw_events`
                # These images are not necessarily saved already
                image_nbs = list(range(first_index, last_index + 1))
                try:
                    data = image_filenames(self.ref_data[0], image_nbs)
                except RuntimeError:
                    # Images are not saved
                    data = list()
                else:
                    self._stream_image_count = last_index + 1
        return EventData(first_index=first_index, data=data, description=ref_status)

    def store(self, event_dict, cnx=None):
        data = event_dict["data"]
        if data.get("in_prepare", False):  # in prepare phase
            desc = event_dict["description"]
            self.info.update(desc)
            self.add_reference_data(desc)
            self._local_ref_status = data
            self._local_ref_status["lima_acq_nb"] = self.db_connection.incr(
                data["server_url"]
            )
        else:  # during acquisition
            self._local_ref_status.update(data)
            self.data.add(
                {self.DATA: pickle.dumps(self._local_ref_status)},
                id=self._last_index,
                cnx=cnx,
            )
            self._last_index += 1

    def add_reference_data(self, ref_data):
        """Save reference data in database

        In case of Lima, this corresponds to acquisition ref_data,
        in particular saving data
        """
        self.data_ref.append(ref_data)

    def get_file_references(self):
        """
        Retrieve all files references for this data set
        """
        # take the last in list because it's should be the final
        final_ref_data = self.data_ref[-1]
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
        db_names = DataNode._get_db_names(self)
        db_names.append(self.db_name + "_data")
        db_names.append(self.db_name + "_data_ref")

        raw_data = self.data.range(count=1)
        if raw_data:
            index, raw_event = raw_data[0]
            raw_ref = pickle.loads(raw_event[self.DATA])
            url = raw_ref.get("server_url")
            if url is not None:
                db_names.append(url)
        return db_names
