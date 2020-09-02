# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Utility functions to read Lima images from file or device server.
"""

import struct
import numpy
import typing
import enum
from silx.third_party.EdfFile import EdfFile


try:
    import h5py
except ImportError:
    h5py = None

DATA_HEADER_FORMAT = "<IHHIIHHHHHHHHHHHHHHHHHHIII"
DATA_MAGIC = struct.unpack(">I", b"DTAY")[0]
DATA_HEADER_SIZE = struct.calcsize(DATA_HEADER_FORMAT)

VIDEO_HEADER_FORMAT = "!IHHqiiHHHH"
VIDEO_MAGIC = struct.unpack(">I", b"VDEO")[0]
VIDEO_HEADER_SIZE = struct.calcsize(VIDEO_HEADER_FORMAT)


class VIDEO_MODES(enum.Enum):
    # From https://github.com/esrf-bliss/Lima/blob/master/common/include/lima/Constants.h#L118
    Y8 = 0
    Y16 = 1
    Y32 = 2
    Y64 = 3
    RGB555 = 4
    RGB565 = 5
    RGB24 = 6
    RGB32 = 7
    BGR24 = 8
    BGR32 = 9
    BAYER_RG8 = 10
    BAYER_RG16 = 11
    BAYER_BG8 = 12
    BAYER_BG16 = 13
    I420 = 14
    YUV411 = 15
    YUV422 = 16
    YUV444 = 17
    YUV411PACKED = 18
    YUV422PACKED = 19
    YUV444PACKED = 20


class IMAGE_MODES(enum.Enum):
    DARRAY_UINT8 = 0
    DARRAY_UINT16 = 1
    DARRAY_UINT32 = 2
    DARRAY_UINT64 = 3
    DARRAY_INT8 = 4
    DARRAY_INT16 = 5
    DARRAY_INT32 = 6
    DARRAY_INT64 = 7
    DARRAY_FLOAT32 = 8
    DARRAY_FLOAT64 = 9


# Mapping used for direct conversion from raw data to numpy array
MODE_TO_NUMPY = {
    IMAGE_MODES.DARRAY_UINT8: numpy.uint8,
    IMAGE_MODES.DARRAY_UINT16: numpy.uint16,
    IMAGE_MODES.DARRAY_UINT32: numpy.uint32,
    IMAGE_MODES.DARRAY_UINT64: numpy.uint64,
    IMAGE_MODES.DARRAY_INT8: numpy.int8,
    IMAGE_MODES.DARRAY_INT16: numpy.int16,
    IMAGE_MODES.DARRAY_INT32: numpy.int32,
    IMAGE_MODES.DARRAY_INT64: numpy.int64,
    IMAGE_MODES.DARRAY_FLOAT32: numpy.float32,
    IMAGE_MODES.DARRAY_FLOAT64: numpy.float64,
    VIDEO_MODES.Y8: numpy.uint8,
    VIDEO_MODES.Y16: numpy.uint16,
    VIDEO_MODES.Y32: numpy.int32,
    VIDEO_MODES.Y64: numpy.int64,
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


def decode_devencoded_video(
    raw_data: bytes
) -> typing.Optional[typing.Tuple[numpy.ndarray, int]]:
    """Decode data provided by Lima device video attribute.

    See https://lima1.readthedocs.io/en/latest/applications/tango/python/doc/#devencoded-video-image

    Argument:
        raw_data: Data returns by Lima video attribute

    Returns:
        A tuple with the frame data (as a numpy array), and the frame number
        if an image is available. None if there is not yet acquired image.

    Raises:
        ImageFormatNotSupported: when the retrieved data is not supported
    """
    if isinstance(raw_data, tuple):
        # Support the direct output from proxy.video_last_image
        if raw_data[0] != "VIDEO_IMAGE":
            raise ImageFormatNotSupported(
                "Data type VIDEO_IMAGE expected (found %s)." % raw_data[0]
            )
        raw_data = raw_data[1]

    if len(raw_data) < VIDEO_HEADER_SIZE:
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
    ) = struct.unpack(VIDEO_HEADER_FORMAT, raw_data[:VIDEO_HEADER_SIZE])

    if magic != VIDEO_MAGIC:
        raise ImageFormatNotSupported(
            "Magic header not supported (found 0x%x)." % magic
        )

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

    try:
        mode = VIDEO_MODES(image_mode)
    except Exception:
        raise ImageFormatNotSupported(
            "Video format unsupported (found %s)." % image_mode
        )

    try:
        dtype = MODE_TO_NUMPY[mode]
    except Exception:
        raise ImageFormatNotSupported("Video format %s is not supported" % mode)

    data = numpy.frombuffer(raw_data[header_size:], dtype=dtype).copy()
    data.shape = image_height, image_width
    return data, image_frame_number


def decode_devencoded_image(raw_data: bytes) -> numpy.ndarray:
    """Decode data provided by Lima device image attribute

    See https://lima1.readthedocs.io/en/latest/applications/tango/python/doc/#devencoded-data-array

    Argument:
        raw_data: Data returns by Lima image attribute

    Returns:
        A numpy array else None if there is not yet acquired image.

    Raises:
        ImageFormatNotSupported: when the retrieved data is not supported
    """
    if isinstance(raw_data, tuple):
        # Support the direct output from proxy.readImage
        if raw_data[0] != "DATA_ARRAY":
            raise ImageFormatNotSupported(
                "Data type DATA_ARRAY expected (found %s)." % raw_data[0]
            )
        raw_data = raw_data[1]

    (
        magic,
        version,
        header_size,
        _category,
        data_type,
        endianness,
        nb_dim,
        dim1,
        dim2,
        _dim3,
        _dim4,
        _dim5,
        _dim6,
        _dim7,
        _dim8,
        _dim_step1,
        _dim_step2,
        _dim_step3,
        _dim_step4,
        _dim_step5,
        _dim_step6,
        _dim_step7,
        _dim_step8,
        _pad0,
        _pad1,
        _pad2,
    ) = struct.unpack(DATA_HEADER_FORMAT, raw_data[:DATA_HEADER_SIZE])

    if magic != DATA_MAGIC:
        raise ImageFormatNotSupported(
            "Magic header not supported (found 0x%x)." % magic
        )
    if version not in [1, 2]:
        raise ImageFormatNotSupported(
            "Image header version not supported (found %s)." % version
        )

    try:
        mode = IMAGE_MODES(data_type)
    except Exception:
        raise ImageFormatNotSupported(
            "Image format from Lima Tango device not supported (found %s)." % data_type
        )
    if endianness != 0:
        raise ImageFormatNotSupported("Unsupported endianness (found %s)." % endianness)

    if nb_dim != 2:
        raise ImageFormatNotSupported(
            "Image header nb_dim==2 expected (found %s)." % nb_dim
        )

    try:
        dtype = MODE_TO_NUMPY[mode]
    except Exception:
        raise ImageFormatNotSupported("Data format %s is not supported" % mode)

    data = numpy.fromstring(raw_data[header_size:], dtype=dtype)
    data.shape = dim2, dim1
    return data


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
    decoded = decode_devencoded_video(raw_data)
    return decoded


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

    array = decode_devencoded_image(raw_msg)
    return array


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
