# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Utility functions to read Lima images from file or server.
"""

import struct
import numpy
import typing
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


def image_from_server(proxy, image_nb: int) -> numpy.ndarray:
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


def image_from_file(filename, path_in_file, image_index, file_format):
    """
    :param str filename:
    :param str path_in_file:
    :param int image_index: for multi-frame formats
    :param str file_format: HDF5, HDF5BS, EDFLZ4, ...
                            This is not the file extension!
    """
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