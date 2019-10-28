# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import struct
import math
import numpy
import gevent
from bliss.common.tango import DeviceProxy
from bliss.common.task import task
from bliss.data.node import DataNode
from bliss.config.settings import QueueObjSetting
from silx.third_party.EdfFile import EdfFile

try:
    import h5py
except ImportError:
    h5py = None

VIDEO_HEADER_FORMAT = "!IHHqiiHHHH"
HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)


class LimaImageChannelDataNode(DataNode):
    class LimaDataView(object):
        DataArrayMagic = struct.unpack(">I", b"DTAY")[0]

        def __init__(self, data, from_index, to_index, from_stream=False):
            self.data = data
            self.from_index = from_index
            self.to_index = to_index
            self.last_image_ready = -1
            self.from_stream = from_stream
            self._image_mode = {
                0: numpy.uint8,
                1: numpy.uint16,
                2: numpy.uint32,
                4: numpy.int8,
                5: numpy.int16,
                6: numpy.int32,
            }

        @property
        def ref_status(self):
            return self.data[0]

        @property
        def ref_data(self):
            return self.data[1:]

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

        def get_last_live_image(self, proxy=0, update=True):
            """Returns the last image data from stream within it's frame number.

            If no data is available, the function returns tuple (None, None).
            """
            if update:
                self._update()

            if proxy == 0:
                # 0 is used to discriminate with None, which can be passed
                proxy = self._get_proxy()

            if not proxy:
                return None, None

            if not self.from_stream:
                return None, None

            # get last video image
            _, raw_data = proxy.video_last_image
            if len(raw_data) <= HEADER_SIZE:
                return None, None

            (
                magic,
                header_version,
                image_mode,
                image_frameNumber,
                image_width,
                image_height,
                endian,
                header_size,
                pad0,
                pad1,
            ) = struct.unpack(VIDEO_HEADER_FORMAT, raw_data[:HEADER_SIZE])

            if magic != 0x5644454f or header_version != 1:
                raise IndexError("Bad image header.")
            if image_frameNumber < 0:
                raise IndexError("Image (from Lima live interface) not available yet.")

            video_modes = (numpy.uint8, numpy.uint16, numpy.int32, numpy.int64)
            try:
                mode = video_modes[image_mode]
            except IndexError:
                raise IndexError("Unknown image mode (found %s)." % image_mode)

            data = numpy.frombuffer(raw_data[HEADER_SIZE:], dtype=mode).copy()
            data.shape = image_height, image_width

            # FIXME: Some detectors (like andor) which do not provide TRIGGER_SOFT_MULTI
            # Will always returns frame_id = 0. In this case it would be better to return
            # None as the frame_id

            return data, image_frameNumber

        def get_image(self, image_nb, proxy=0):
            self._update()

            if proxy == 0:
                # 0 is used to discriminate with None, which can be passed
                proxy = self._get_proxy()

            data = None
            if proxy:
                if self.from_stream and image_nb == -1:
                    data, _frame_id = self.get_last_live_image(
                        proxy=proxy, update=False
                    )
                if data is None:
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

        def _get_filenames(self, ref_data, *image_nbs):
            saving_mode = ref_data.get("saving_mode", "MANUAL")
            if saving_mode == "MANUAL":  # files are not saved
                raise RuntimeError("Images were not saved")

            overwrite_policy = ref_data.get("saving_overwrite", "ABORT").lower()
            if overwrite_policy == "multiset":
                nb_image_per_file = ref_data["acq_nb_frames"]
            else:
                nb_image_per_file = ref_data.get("saving_frame_per_file", 1)

            last_image_saved = self.last_image_saved
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
            for image_nb in image_nbs:
                if image_nb > last_image_saved:
                    raise RuntimeError("Image %d was not saved" % image_nb)

                image_index_in_file = image_nb % nb_image_per_file
                file_nb = first_file_number + image_nb // nb_image_per_file
                file_path = path_format % file_nb
                if file_format == "HDF5":
                    returned_params.append(
                        (file_path, "/entry_%04d" % 0, image_index_in_file, file_format)
                    )
                else:
                    returned_params.append(
                        (file_path, "", image_index_in_file, file_format)
                    )
            return returned_params

        def _get_from_file(self, image_nb):
            for ref_data in self.ref_data:
                values = self._get_filenames(ref_data, image_nb)
                filename, path_in_file, image_index, file_format = values[0]

                if file_format in ("EDF", "EDFGZ", "EDFConcat"):
                    if file_format == "EDFConcat":
                        image_index = 0
                    if EdfFile is not None:
                        f = EdfFile(filename)
                        return f.GetData(image_index)
                    else:
                        raise RuntimeError(
                            "EdfFile module is not available, "
                            "cannot return image data."
                        )
                elif file_format == "HDF5":
                    if h5py is not None:
                        with h5py.File(filename) as f:
                            dataset = f[path_in_file]
                            return dataset[image_index]
                else:
                    raise RuntimeError("Format not managed yet")
            else:
                raise IndexError("Cannot retrieve image %d from file" % image_nb)

        def _tango_unpack(self, msg):
            struct_format = "<IHHIIHHHHHHHHHHHHHHHHHHIII"
            header_size = struct.calcsize(struct_format)
            values = struct.unpack(struct_format, msg[:header_size])
            if values[0] != self.DataArrayMagic:
                raise RuntimeError("No Lima data")
            header_offset = values[2]
            data = numpy.fromstring(
                msg[header_offset:], dtype=self._image_mode.get(values[4])
            )
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

        self.data = QueueObjSetting(
            "%s_data" % self.db_name, connection=self.db_connection
        )
        self._new_image_status_event = gevent.event.Event()
        self._new_image_status = dict()
        self._storage_task = None
        self.from_stream = False

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

    def __close__(self):
        if self._storage_task is None:
            return
        storage_task = self._storage_task
        storage_task.join(timeout=3.)
        storage_task.kill()
        self._storage_task = None

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
            from_index,
            to_index if to_index is not None else from_index + 1,
            from_stream=self.from_stream,
        )

    def store(self, event_dict):
        desc = event_dict["description"]
        data = event_dict["data"]
        if self._storage_task is None:
            self._storage_task = self._do_store(wait=False, wait_started=True)

        try:
            self.data[0]
        except IndexError:
            ref_status = data
            ref_status["lima_acq_nb"] = self.db_connection.incr(data["server_url"])
            self.data.append(ref_status)
            self.add_reference_data(desc)
        else:
            self.info.update(desc)

            self._new_image_status.update(data)
            self._new_image_status_event.set()

    @task
    def _do_store(self):
        try:
            while True:
                self._new_image_status_event.wait()
                self._new_image_status_event.clear()
                local_dict = self._new_image_status
                self._new_image_status = dict()
                ref_status = self.data[0]
                ref_status.update(local_dict)
                self.data[0] = ref_status
                if local_dict["acq_state"] in ("fault", "ready"):
                    break
                gevent.idle()
        finally:
            self._storage_task = None

    def add_reference_data(self, ref_data):
        """Save reference data in database

        In case of Lima, this corresponds to acquisition ref_data,
        in particular saving data
        """
        self.data.append(ref_data)

    def get_file_references(self):
        """
        Retrieve all files references for this data set
        """
        # take the last in list because it's should be the final
        final_ref_data = self.data[-1]
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
            if file_format == "hdf5":
                # @todo see what's is needed for hdf5 dataset link
                pass
            references.append(full_path)
        return references

    def _get_db_names(self):
        db_names = DataNode._get_db_names(self)
        db_names.append(self.db_name + "_data")
        try:
            url = self.data[0].get("server_url")
        except IndexError:
            url = None
        if url is not None:
            db_names.append(url)
        return db_names