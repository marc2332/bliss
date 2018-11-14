# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import usb
import sys
import time
import math
import array
import struct
import select
import gevent
import gevent.event
import gevent.queue
import gevent.select
import numpy as np
import atexit

from ctypes import (
    cast,
    c_int,
    c_uint16,
    c_short,
    c_ulong,
    c_ubyte,
    c_void_p,
    POINTER,
    pointer,
    py_object,
    byref,
    addressof,
    Structure,
    CDLL,
    CFUNCTYPE,
)
from functools import reduce

libc = CDLL("libc.so.6")
libc.free.argtypes = [c_void_p]


class ImageRGB(object):
    def __init__(self, img_size=(0, 0), img_data=None, img_depth=3):
        self._depth = img_depth
        self._size = img_size
        self.data = img_data

    @property
    def depth(self):
        return self._depth

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, img_size):
        self._size = img_size
        if self.data and len(self.data) != self.bytes:
            self.data = None

    @property
    def cols(self):
        return self._size[0]

    @property
    def rows(self):
        return self._size[1]

    @property
    def bytes(self):
        return self.cols * self.rows * self.depth

    @property
    def data(self):
        if not self._data and self.bytes:
            self._data = bytearray(self.bytes)
        return self._data

    @data.setter
    def data(self, img_data):
        if img_data and len(img_data) != self.bytes:
            raise ValueError("Image size/data length mismatch")
        self._data = img_data

    def data_aligned(self, align_bit=32):
        real_line_bytes = self.cols * self.depth
        align = align_bit / 8
        aligned_line_bytes = int((real_line_bytes + align - 1) / align) * align

        a = np.fromstring(self.data, dtype="uint8")
        a.resize((self.rows, real_line_bytes))
        b = np.zeros((self.rows, aligned_line_bytes), "uint8")
        b[:, :real_line_bytes] = a
        return b.tostring()

    @property
    def np_array(self):
        data = np.fromstring(self.data, dtype="uint8")
        data.resize((self.rows, self.cols, self.depth))
        return data

    def get_binned(self, ibin):
        data = self.np_array
        bin_x, bin_y = ibin
        if bin_x == 1 and bin_y == 1:
            return ImageRGB((self.cols, self.rows), self.data.tostring())
        if self.cols % bin_x != 0 or self.rows % bin_y != 0:
            raise ValueError("Invalid bin: must be a multiple of dims")
        new_cols = self.cols / bin_x
        new_rows = self.rows / bin_y
        xquad = 2
        yquad = 2
        x1 = int((new_cols + xquad - 1) / xquad)
        x2 = new_cols - x1 * (xquad - 1)
        y1 = int((new_rows + yquad - 1) / yquad)
        y2 = new_rows - y1 * (yquad - 1)
        xblocks = [x1] * (xquad - 1) + [x2]
        yblocks = [y1] * (yquad - 1) + [y2]
        gthreadpool = gevent.get_hub().threadpool
        tasks = []
        t0 = time.time()
        new_data = np.zeros((new_rows, new_cols, 3), "uint8")
        y0 = 0
        for y in yblocks:
            x0 = 0
            for x in xblocks:
                ox0, oy0 = x0 * bin_x, y0 * bin_y
                ox, oy = x * bin_x, y * bin_y
                qd = data[oy0 : oy0 + oy, ox0 : ox0 + ox]
                qr = new_data[y0 : y0 + y, x0 : x0 + x]
                t = gthreadpool.spawn(
                    self.get_binned_quadrant, *(qd, (bin_x, bin_y), qr)
                )
                tasks.append(t)
                x0 += x
            y0 += y
        gevent.wait(tasks)
        # print "get_binned: %s sec" % (time.time() - t0)
        return ImageRGB((new_cols, new_rows), new_data.tostring())

    def get_binned_quadrant(self, data, ibin, res):
        rows, cols, depth = data.shape
        bin_x, bin_y = ibin
        if cols % bin_x != 0 or rows % bin_y != 0:
            raise ValueError("Invalid bin: must be a multiple of dims")
        new_cols = cols / bin_x
        new_rows = rows / bin_y
        aux_shape = (new_rows, bin_y, new_cols, bin_x, depth)
        new_data = data.reshape(aux_shape).sum(3).sum(1) / (bin_x * bin_y)
        res[:] = np.array(new_data, res.dtype)

    def get_qtimage(self):
        return QtGui.QImage(
            self.data_aligned(), self.cols, self.rows, QtGui.QImage.Format_RGB888
        )

    def save_to_file(self, fname):
        im = Image.frombuffer("RGB", self.size, self.data)
        im.save(fname)

    @staticmethod
    def load_from_jpeg(fname):
        ifile = JpegImageFile(fname)
        ifile.load()
        return ImageRGB(ifile.size, ifile.tobytes())

    @staticmethod
    def gen_color_pattern(isize, i=0):
        cols, rows = isize
        a = np.zeros((rows, cols, 3), "uint8")
        for x in range(cols):
            for y in range(rows):
                v = (x + y) % 2 ** 8
                a[y][x] = [v, 2 ** 8 - v, abs((v + i - 2 ** 7) % 2 ** 8)]
        return ImageRGB(isize, a.tostring())


class USBDeviceEventLoop(object):

    UsePoll = False

    def __init__(self, dev):
        self.ctx = dev._ctx.backend.ctx
        self.queue = gevent.queue.Queue()
        self.task = None
        self.start()

    def __del__(self):
        self.stop()

    def start(self):
        if not self.task:
            self.task = gevent.spawn(self.event_loop_funct)

    def stop(self):
        if self.task:
            self.queue.put(None)
            self.task.join()
            self.task = None

    def submit(self, transfer):
        done_event = gevent.event.Event()
        self.queue.put((transfer, done_event))
        return done_event

    def event_loop_funct(self):
        self.pollfd_init()
        self.pollfd_notifiers(True)

        self.transfers = []

        while self.receive_requests():
            self.pollfd_poll()
            _check(_lib.libusb_handle_events(self.ctx))

        self.pollfd_notifiers(False)

    def receive_requests(self):
        cb_p = _libusb_transfer_cb_fn_p(self.callback)
        while True:
            try:
                block = not self.transfers
                data = self.queue.get(block)
            except gevent.queue.Empty:
                return True
            else:
                if data is None:
                    return False
                transfer, done_event = data
                self.transfers.append(done_event)
                transfer.contents.user_data = py_object(done_event)
                transfer.contents.callback = cb_p
                _check(_lib.libusb_submit_transfer(transfer))

    def pollfd_init(self):
        if self.UsePoll:
            self.poll_obj = gevent.select.poll()
        else:
            self.selectfd_lists = [], [], []

        def pollfds(res):
            i = 0
            while res[i]:
                yield res[i].contents
                i += 1

        res = _lib.libusb_get_pollfds(self.ctx)
        for pollfd in pollfds(res):
            self.pollfd_add(pollfd.fd, pollfd.events)
        libc.free(res)

    def pollfd_notifiers(self, active):
        if active:
            add_p = _lib._libusb_pollfd_added_cb_fn_p(self.pollfd_add)
            remove_p = _lib._libusb_pollfd_removed_cb_fn_p(self.pollfd_remove)
        else:
            add_p = _lib._libusb_pollfd_added_cb_fn_p()
            remove_p = _lib._libusb_pollfd_removed_cb_fn_p()
        _lib.libusb_set_pollfd_notifiers(self.ctx, add_p, remove_p, None)

    def pollfd_add(self, fd, events, data=None):
        if self.UsePoll:
            self.poll_obj.register(fd, events)
        else:
            if events & (select.POLLIN | select.POLLPRI):
                self.selectfd_lists[0].append(fd)
            if events & select.POLLOUT:
                self.selectfd_lists[1].append(fd)
            if events & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
                self.selectfd_lists[2].append(fd)

    def pollfd_remove(self, fd, data=None):
        if self.UsePoll:
            self.poll_obj.unregister(fd)
        else:
            for fdlist in self.selectfd_lists:
                if fd in fdlist:
                    fdlist.remove(fd)

    def pollfd_poll(self):
        if self.UsePoll:
            self.poll_obj.poll()
        else:
            gevent.select.select(*self.selectfd_lists)

    def callback(self, transfer):
        done_event = transfer.contents.user_data
        self.transfers.remove(done_event)
        done_event.set()


_lib = None
_libusb_transfer_p = None
_libusb_transfer_cb_fn_p = None
_check = None
_str_transfer_error = None
_transfer_errno = None
_LIBUSB_TRANSFER_TYPE_BULK = None
LIBUSB_TRANSFER_COMPLETED = None
LIBUSB_ERROR_TIMEOUT = None


def update_libusb_globals(libusb):
    global _lib
    _lib = libusb._lib
    global _libusb_transfer_p
    _libusb_transfer_p = libusb._libusb_transfer_p
    global _libusb_transfer_cb_fn_p
    _libusb_transfer_cb_fn_p = libusb._libusb_transfer_cb_fn_p
    global _check
    _check = libusb._check
    global _str_transfer_error
    _str_transfer_error = libusb._str_transfer_error
    global _transfer_errno
    _transfer_errno = libusb._transfer_errno
    global _LIBUSB_TRANSFER_TYPE_BULK
    _LIBUSB_TRANSFER_TYPE_BULK = libusb._LIBUSB_TRANSFER_TYPE_BULK
    global LIBUSB_TRANSFER_COMPLETED
    LIBUSB_TRANSFER_COMPLETED = libusb.LIBUSB_TRANSFER_COMPLETED
    global LIBUSB_ERROR_TIMEOUT
    LIBUSB_ERROR_TIMEOUT = libusb.LIBUSB_ERROR_TIMEOUT

    # Missing function declarations
    lib = _lib

    # static void libusb_fill_bulk_transfer 	(
    # 		struct libusb_transfer *  	transfer,
    # 		libusb_device_handle *  	dev_handle,
    # 		unsigned char		  	endpoint,
    # 		unsigned char *  		buffer,
    # 		int 			 	length,
    # 		libusb_transfer_cb_fn 	 	callback,
    # 		void * 				user_data,
    # 		unsigned int 		 	timeout
    # 	)

    def libusb_fill_bulk_transfer(
        _libusb_transfer_p,
        dev_handle,
        endpoint,
        buffer,
        length,
        callback,
        user_data,
        timeout,
    ):
        r"""This function is inline in the libusb.h file, so we must implement
            it.

        lib.libusb_fill_bulk_transfer.argtypes = [
                       _libusb_transfer,
                       _libusb_device_handle,
                       c_ubyte,
                       POINTER(c_ubyte),
                       c_int,
                       _libusb_transfer_cb_fn_p,
                       c_void_p,
                       c_uint
                   ]
        """
        transfer = _libusb_transfer_p.contents
        transfer.dev_handle = dev_handle
        transfer.endpoint = endpoint
        transfer.type = _LIBUSB_TRANSFER_TYPE_BULK
        transfer.timeout = timeout
        transfer.buffer = cast(buffer, c_void_p)
        transfer.length = length
        transfer.user_data = user_data
        transfer.callback = callback

    lib.libusb_fill_bulk_transfer = libusb_fill_bulk_transfer

    class _libusb_pollfd(Structure):
        _fields_ = [("fd", c_int), ("events", c_uint16)]

    lib._libusb_pollfd = _libusb_pollfd

    # struct libusb_pollfd** libusb_get_pollfds(libusb_context *ctx)
    lib.libusb_get_pollfds.argtypes = [c_void_p]
    lib.libusb_get_pollfds.restype = POINTER(POINTER(_libusb_pollfd))

    # typedef void(*libusb_pollfd_added_cb)(int fd, short events,
    # 					    void *user_data)
    lib._libusb_pollfd_added_cb_fn_p = CFUNCTYPE(None, c_int, c_short, py_object)
    # typedef void(*libusb_pollfd_removed_cb)(int fd, void *user_data)
    lib._libusb_pollfd_removed_cb_fn_p = CFUNCTYPE(None, c_int, py_object)

    # void libusb_set_pollfd_notifiers 	(
    # 		libusb_context *	  	ctx,
    # 		libusb_pollfd_added_cb  	added_cb,
    # 		libusb_pollfd_removed_cb  	removed_cb,
    # 		void *  	user_data
    # 	)
    lib.libusb_set_pollfd_notifiers.argtypes = [
        c_void_p,
        lib._libusb_pollfd_added_cb_fn_p,
        lib._libusb_pollfd_removed_cb_fn_p,
        py_object,
    ]


class _BulkTransferHandler(object):
    def __init__(self, dev, dev_handle, ep, buff, timeout):
        cntx = dev._ctx
        self.lib = cntx.backend
        if self.lib.__module__ != "usb.backend.libusb1":
            raise NotImplementedError("Only libusb1 backend supported")

        self.libusb = sys.modules[self.lib.__module__]
        if _lib is None:
            update_libusb_globals(self.libusb)

        address, length = buff.buffer_info()
        self.transfer = _lib.libusb_alloc_transfer(0)
        _lib.libusb_fill_bulk_transfer(
            self.transfer,
            dev_handle.handle,
            ep,
            cast(address, POINTER(c_ubyte)),
            length,
            _libusb_transfer_cb_fn_p(),
            None,
            timeout,
        )

    def __del__(self):
        _lib.libusb_free_transfer(self.transfer)

    def submit(self, loop):
        done_event = loop.submit(self.transfer)
        done_event.wait()

        if self.transfer.contents.status == LIBUSB_TRANSFER_COMPLETED:
            ret = self.transfer.contents.actual_length
        else:
            status = int(self.transfer.contents.status)
            raise usb.USBError(
                _str_transfer_error[status], status, _transfer_errno[status]
            )
        return ret


class BulkEndpoint(object):
    def __init__(self, ep, loop):
        self.ep = ep
        self.dev = self.ep.device
        self.cntx = self.dev._ctx
        self.loop = loop

    def write(self, data, timeout=None):
        intf, ep = self.cntx.setup_request(self.dev, self.ep)
        buff = usb._interop.as_array(data)
        get_timeout = getattr(self.dev, "_Device__get_timeout")
        transfer = _BulkTransferHandler(
            self.dev, self.cntx.handle, ep.bEndpointAddress, buff, get_timeout(timeout)
        )
        ret = transfer.submit(self.loop)
        return ret

    def read(self, size_or_buffer, timeout=None):
        intf, ep = self.cntx.setup_request(self.dev, self.ep)
        if isinstance(size_or_buffer, array.array):
            buff = size_or_buffer
        else:
            buff = usb.util.create_buffer(size_or_buffer)

        get_timeout = getattr(self.dev, "_Device__get_timeout")
        transfer = _BulkTransferHandler(
            self.dev, self.cntx.handle, ep.bEndpointAddress, buff, get_timeout(timeout)
        )
        ret = transfer.submit(self.loop)
        if isinstance(size_or_buffer, array.array):
            return ret
        elif ret != len(buff) * buff.itemsize:
            return buff[:ret]
        else:
            return buff

    @property
    def raw_endpoint(self):
        return self.ep

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.ep, name)


class USBDev(object):

    EP_IN = usb.util.ENDPOINT_IN
    EP_OUT = usb.util.ENDPOINT_OUT

    EP_CTRL = usb.util.ENDPOINT_TYPE_CTRL
    EP_ISO = usb.util.ENDPOINT_TYPE_ISO
    EP_BULK = usb.util.ENDPOINT_TYPE_BULK
    EP_INTR = usb.util.ENDPOINT_TYPE_INTR

    def __init__(self, usb_dev=None, vendor_id=None, product_id=None):
        self.loop = None
        if usb_dev is None:
            if None in [vendor_id, product_id]:
                raise ValueError("Must provide either usb_dev or vendor/product")
            usb_dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
            if usb_dev is None:
                raise RuntimeError(
                    "Could not find USB device %04x:%04x" % (vendor_id, product_id)
                )
        self.dev = usb_dev
        self.dev.set_configuration()
        self.cfg = self.dev.get_active_configuration()

    def __del__(self):
        if self.loop:
            self.loop.stop()

    def reset(self):
        self.dev.reset()

    def get_end_point(
        self, iface_nb, ep_nb=None, ep_dir=None, ep_type=None, green=True
    ):
        def match(e):
            if (
                ep_nb is not None
                and usb.util.endpoint_address(e.bEndpointAddress) != ep_nb
            ):
                return False
            if (
                ep_dir is not None
                and usb.util.endpoint_direction(e.bEndpointAddress) != ep_dir
            ):
                return False
            if (
                ep_type is not None
                and usb.util.endpoint_type(e.bmAttributes) != ep_type
            ):
                return False
            else:
                return True

        iface = self.cfg[(iface_nb, 0)]
        ep = usb.util.find_descriptor(iface, custom_match=match)
        if not green:
            return ep
        if usb.util.endpoint_type(ep.bmAttributes) == self.EP_BULK:
            if self.loop is None:
                self.loop = USBDeviceEventLoop(self.dev)
            return BulkEndpoint(ep, self.loop)
        else:
            raise NotImplementedError("Only Bulk endpoints are gevent-friendly")

    def clear_halt(self, end_point):
        try:
            raw_endpoint = end_point.raw_endpoint
        except AttributeError:
            raw_endpoint = end_point
        self.dev.clear_halt(raw_endpoint)


class LeicaUSB(object):

    VENDOR_ID = 0x1711

    def __init__(
        self, usb_dev=None, vendor_id=None, product_id=None, reset=False, green=True
    ):
        if vendor_id is None:
            vendor_id = self.VENDOR_ID
        if product_id is None:
            product_id = self.PRODUCT_ID
        self.dev = USBDev(usb_dev, vendor_id, product_id)
        if reset:
            self.dev.reset()
        self.green = green

    def get_end_point(
        self, iface_nb, ep_nb=None, ep_dir=None, ep_type=None, green=None
    ):
        if green is None:
            green = self.green
        return self.dev.get_end_point(iface_nb, ep_nb, ep_dir, ep_type, green)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.dev, name)


class LeicaFocus(LeicaUSB):

    PRODUCT_ID = 0x2403

    CDC_IF_NB = 0

    Motors = [
        ("LED_Int", 37),
        ("Mot_38", 38),
        ("Zoom_Mag", 60),
        ("Iris", 62),
        ("Focus_Coarse", 70),
        ("Focus_Fine", 72),
        ("Mot_81", 81),
        ("Mot_83", 83),
        ("Zoom_Mag_10", 160),
        ("Mot_162", 162),
        ("Mot_164", 164),
        ("Mot_166", 166),
        ("Mot_168", 168),
        ("Mot_170", 170),
        ("Mot_172", 172),
    ]
    locals().update(dict(Motors))

    Zoom_Group = [Zoom_Mag, Zoom_Mag_10, Mot_162]
    Non_Status_Group = [Mot_81, Mot_83, Mot_164, Mot_166, Mot_168, Mot_170, Mot_172]
    ALL_MOTORS = 254
    ALL_MOTORS_LINES = len(Motors) + 1  # 70_34

    # Steps = {LED_Int: 0.1,
    #         Iris: 10,
    #         Focus_Coarse: 1000,
    #         Focus_Fine: 1000,
    #         Zoom_Mag: 100,
    #         Zoom_Mag_10: 1000}

    MOT_REQ_PST = 12
    MOT_REQ_MVA = 30
    MOT_REQ_MVR = 58
    MOT_REQ_POS = 32
    MOT_RES_POS = 32
    MOT_RES_STA = 35

    # Stats
    MOT_STA_IDLE = 0
    MOT_STA_MOV = 1 << 5
    MOT_STA_LIMN = 1 << 6
    MOT_STA_LIMP = 1 << 7

    Cmd = {
        USBDev.EP_OUT: {
            MOT_REQ_PST: "Req.PSt",
            MOT_REQ_MVA: "Req.MvA",
            MOT_REQ_MVR: "Req.MvR",
            MOT_REQ_POS: "Req.Pos",
        },
        USBDev.EP_IN: {MOT_RES_POS: "Res.Pos", MOT_RES_STA: "Res.Sta"},
    }

    Sta = {MOT_STA_MOV: "Moving", MOT_STA_LIMN: "Lim-", MOT_STA_LIMP: "Lim+"}

    def __init__(self, usb_dev=None):
        LeicaUSB.__init__(self, usb_dev, reset=True)

        ep_type = USBDev.EP_BULK
        self.ep_out = self.get_end_point(
            self.CDC_IF_NB, ep_type=ep_type, ep_dir=USBDev.EP_OUT
        )
        self.clear_halt(self.ep_out)
        self.ep_in = self.get_end_point(
            self.CDC_IF_NB, ep_type=ep_type, ep_dir=USBDev.EP_IN
        )
        self.clear_halt(self.ep_in)

        self.mne = {}
        self.dial = {}
        self.status = {}
        self.closed = False

        for mne, num in self.Motors:
            self.mne[num] = mne
            self.dial[num] = None
            self.status[num] = None
            # if num not in self.Steps:
            #    self.Steps[num] = 1

        for b in range(16):
            i = 1 << b
            if i not in self.Sta:
                self.Sta[i] = "Sta.UK%X" % b

        self.nb_req = 1

        self.curr_move = None
        self.close()

        self.write(69, self.Mot_81, 410, 411)
        resp = self.read()
        print("------------------->", type(resp), resp)
        if resp:
            l = list(map(int, resp.split()))
            if l[:4] != [self.Mot_81, 69, 410, 411]:
                raise RuntimeError("Invalid resp")
        else:
            raise RuntimeError("No resp")

        res = self.get_all_mot_pos_status()
        for mne, num in self.Motors:
            pos, status = res[num]
            stat = self.get_status_str(status)
            # print "%13s %10s %s" % (mne + ':', pos, stat)

    def close(self):
        if not self.closed:
            print("---------------------> closing connection")
            try:
                if self.curr_move:
                    self.curr_move.wait()

                if self.nb_req % 2 == 1:
                    print("Balancing Focus USB requests")
                    self.read_mot_pos(self.Iris)
                self.closed = True
            except:
                pass

    def get_all_mot_pos_status(self):
        res = {}
        all_pos = self.read_all_mot_pos()
        for mne, num in self.Motors:
            if num in self.Zoom_Group[1:]:
                continue
            for anum, pos, status in self.read_mot_pos_status(num):
                res[anum] = (pos, status)
        return res

    def switch_led_on(self):
        self.write(95, 37, 1)

    def switch_led_off(self):
        self.write(95, 37, 0)

    def read_all_mot_pos(self, fromcache=False):
        if not fromcache or None in list(self.dial.values()):
            self.write(self.MOT_REQ_POS, self.ALL_MOTORS)
            resp = self.read(multiline=self.ALL_MOTORS_LINES)
            for l in resp:
                fnum, cmd, dial = list(map(float, l.split()))
                num = int(fnum)
                if cmd == self.MOT_RES_POS:
                    self.dial[num] = dial
                    # print num, dial
        pos = dict([(num, dial) for num, dial in list(self.dial.items())])
        return pos

    def read_mot_pos(self, num, fromcache=False):
        if not fromcache or self.dial[num] is None:
            self.write(self.MOT_REQ_POS, num)
            resp = self.read()
            fnum, cmd, dial = list(map(float, resp.split()))
            if cmd != self.MOT_RES_POS:
                raise RuntimeError("Invalid MOT_RES_POS: %s" % resp)
            num = int(fnum)
            self.dial[int(num)] = dial
        return dial  # self.calc_mot_pos(num, dial)

    def read_mot_pos_status(self, num):
        if num in self.Non_Status_Group:
            pos = self.dial[num]  # self.calc_mot_pos(num, self.dial[num])
            return [[num, pos, 0]]
        self.write(self.MOT_REQ_PST, num)
        real_mot = [num]
        lines = 2
        zoom_group = num in self.Zoom_Group
        if zoom_group:
            real_mot = self.Zoom_Group
            lines = 2 * len(real_mot) + 1  # 70_34
        resp = self.read(multiline=lines)
        data = [list(map(float, l.split())) for l in resp]
        res = [([0] * 3) for i in range(len(real_mot))]
        for fnum, cmd, val in data:
            num = int(fnum)
            if cmd not in [self.MOT_RES_STA, self.MOT_RES_POS]:
                continue
            k = real_mot.index(num)
            res[k][0] = num
            if cmd == self.MOT_RES_POS:
                self.dial[num] = val
                res[k][1] = self.dial[num]  # self.calc_mot_pos(num, self.dial[num])
            else:
                self.status[num] = int(val)
                res[k][2] = self.status[num]
        return res

    """def calc_mot_pos(self, num, dial):
        #print num, dial, type(dial)
        return float(dial) / self.Steps[num]

    def calc_mot_dial(self, num, pos):
        return int(pos * self.Steps[num])
    """

    def get_status_str(self, status):
        if status == self.MOT_STA_IDLE:
            return "Idle"
        return ",".join([n for b, n in list(self.Sta.items()) if status & b != 0])

    def start_mot_move(self, num, pos, rel):
        # if self.curr_move:
        #    self.curr_move.wait()
        cmd = self.MOT_REQ_MVR if rel else self.MOT_REQ_MVA
        dial = pos  # self.calc_mot_dial(num, pos)
        self.write(cmd, num, dial)
        # gevent.spawn(self.read, multiline=True) #res = self.read(multiline=True)
        self.curr_move = gevent.spawn(self.read, multiline=True)
        # print "res=%s" % res
        # self.curr_move = gevent.spawn(self.poll_mot_move, num)
        # return self.curr_move

    # def poll_mot_move(self, num):
    #    while True:
    #        for anum, pos, status in self.read_mot_pos_status(num):
    #            if status & self.MOT_STA_MOV:
    #                break
    #        else:
    #            break
    #    #print "Finished move"

    def write(self, cmd, mot, *args):
        s = " ".join(["%d" % x for x in [mot, cmd] + list(args)])
        # print 'Write: %s' % s
        self.ep_out.write(s + "\r")
        self.nb_req += 1

    def read(self, multiline=False):
        res = []
        while type(multiline) is bool or len(res) < multiline:
            try:
                s = bytearray(self.ep_in.read(1024)).strip()
                s = s.split("\r\n")[0]
                if multiline is False:
                    # print 'Read: %s' % s
                    return s
                if s not in res:
                    res.append(s)
            except:
                # raise
                break
        # for i, s in enumerate(res):
        #    print "Read+ [%d]: '%s'" % (i, s)
        #    pass
        return res


class LeicaCamCtrlPacket(object):

    HEADER = "<cccccBBBHH"
    MAGIC = "U3VC\x00", 0x08

    HOST = 0x40
    DEV = 0x00

    HOST_PACKET_LEN = 12

    TYPE = {HOST: {"Get": 0, "Set": 2}, DEV: {"Get": 1, "Set": 3}}

    def __init__(
        self, ptype=None, pnb=None, addr=None, rlen=None, val=None, rdata=None
    ):
        self.ptype = ptype
        self.pnb = pnb
        self.addr = addr
        self.rlen = rlen
        self.val = val
        self.rdata = rdata

    def tobytes(self):
        src, cmd = self.getSrcCmd(self.ptype)
        data_len = self.HOST_PACKET_LEN if src == self.HOST else len(self.rdata)
        p = list(self.MAGIC[0])
        p += [src, self.ptype, self.MAGIC[1], data_len, self.pnb]
        s = struct.pack(self.HEADER, *p)
        if src == self.HOST:
            s += struct.pack("IBBBB", 0, *self.addr)
            if cmd == "Get":
                s += struct.pack("HH", 0, self.rlen)
            else:
                s += struct.pack("I", self.val)
        else:
            s += bytearray(self.rdata)
        return s

    def __str__(self):
        src, cmd = self.getSrcCmd(self.ptype)
        ptype = cmd + ("Req" if src == self.HOST else "Ack")
        s = "pnb=%04x,ptype=%s[%02x]," % (self.pnb, ptype, self.ptype)
        if src == self.HOST:
            s += "addr=[%s]," % ",".join(["%02x" % x for x in self.addr])
            if cmd == "Get":
                s += "rlen=%d" % self.rlen
            else:
                s += "val=%08x" % self.val
        else:
            data_len = len(self.rdata)
            if data_len == 4:
                s += "rdata=%08x" % struct.unpack("I", self.rdata)
            elif data_len == 8:
                s += "rdata=%016x" % struct.unpack("Q", self.rdata)
            else:
                s += "rdata=<%d bytes>" % data_len
        return "<%s>" % s

    @classmethod
    def getSrcCmd(klass, ptype):
        return [
            (x, y)
            for x in klass.TYPE
            for y, p in list(klass.TYPE[x].items())
            if p == ptype
        ][0]

    @classmethod
    def frombytes(klass, s):
        head_len = struct.calcsize(klass.HEADER)
        d = struct.unpack(klass.HEADER, s[:head_len])
        if ("".join(d[:5]) != klass.MAGIC[0]) or (d[7] != klass.MAGIC[1]):
            raise ValueError("Could not find signatures in header")
        src = d[5]
        if src not in [klass.HOST, klass.DEV]:
            raise ValueError("Invalid packet sender")
        ptype = d[6]
        asrc, cmd = klass.getSrcCmd(ptype)
        if asrc != src:
            raise ValueError("Invalid packet type")
        data_len = d[8]
        pnb = d[9]
        data = s[head_len:]
        if data_len != len(data):
            raise ValueError("Packet length mismatch")
        addr = rlen = val = rdata = None
        if src == klass.HOST:
            if data_len != klass.HOST_PACKET_LEN:
                raise ValueError("Bad host packet length: %s" % data_len)
            if struct.unpack("I", data[:4]) != (0,):
                raise ValueError("Invalid host packet")
            addr = struct.unpack("BBBB", data[4:8])
            if cmd == "Get":
                if struct.unpack("H", data[8:10]) != (0,):
                    raise ValueError("Invalid host packet")
                rlen = struct.unpack("H", data[10:])[0]
            else:
                val = struct.unpack("I", data[8:])[0]
        else:
            rdata = data
        return klass(ptype=ptype, pnb=pnb, addr=addr, rlen=rlen, val=val, rdata=rdata)


class LeicaCamImgPacketI(object):

    HEADER = "<cccccBBBHQBBQHHHHHHQI"
    MAGIC = "U3VL4", 0x01, 0x01, 0x40, 0x0014, 0x0218

    CLOCK_FREQ = 500e6

    def __init__(self, pnb=None, tstamp=None, width=None, height=None):
        self.pnb = pnb
        self.tstamp = tstamp
        self.width = width
        self.height = height

    def tobytes(self):
        p = list(self.MAGIC[0])
        p += [
            0,
            0,
            MAGIC[1],
            self.pnb,
            0,
            MAGIC[2],
            MAGIC[3],
            self.tstamp,
            MAGIC[4],
            MAGIC[5],
            self.width,
            0,
            self.height,
            0,
            0,
            0,
        ]
        return struct.pack(self.HEADER, *p)

    def __str__(self):
        t = self.tstamp / self.CLOCK_FREQ
        s = "pnb=%04x,tstamp=%.6f,width=%d,height=%d" % (
            self.pnb,
            t,
            self.width,
            self.height,
        )
        return "<%s>" % s

    @classmethod
    def frombytes(klass, s):
        d = struct.unpack(klass.HEADER, s)
        if (
            "".join(d[:5]) != klass.MAGIC[0]
            or d[5:8] != (0, 0, klass.MAGIC[1])
            or d[9] != 0
            or d[10:12] != klass.MAGIC[2:4]
            or d[13:15] != klass.MAGIC[4:6]
            or 0 not in (d[16], d[18], d[19], d[20])
        ):
            raise ValueError("Could not find signatures in header")
        pnb = d[8]
        tstamp = d[12]
        width = d[15]
        height = d[17]
        return klass(pnb=pnb, tstamp=tstamp, width=width, height=height)


class LeicaCamImgPacketII(object):

    HEADER = "<cccccBBBHHIIHH"
    MAGIC = "U3VT\x00", 0x02, 0x18

    def __init__(self, plen=None, height=None):
        self.plen = plen
        self.height = height

    def tobytes(self):
        p = list(self.MAGIC[0])
        p += [0, 0, MAGIC[1], MAGIC[2], 0, self.plen, 0, self.height, 0]
        return struct.pack(self.HEADER, *p)

    def __str__(self):
        s = "plen=%04x,height=%d" % (self.plen, self.height)
        return "<%s>" % s

    @classmethod
    def frombytes(klass, s):
        d = struct.unpack(klass.HEADER, s)
        if (
            "".join(d[:5]) != klass.MAGIC[0]
            or d[5:10] != (0, 0, klass.MAGIC[1], klass.MAGIC[2], 0)
            or 0 not in (d[11], d[13])
        ):
            raise ValueError("Could not find signatures in header")
        plen = d[10]
        height = d[12]
        return klass(plen=plen, height=height)


class LeicaCamera(LeicaUSB):

    PRODUCT_ID = 0x2000

    CFG_IF_NB = 0
    IMG_IF_NB = 2

    EXTRA_PIXELS = 90
    ALIGN = 16

    FORMAT_18_02 = "QBBBBIHHI"
    MAX_BLOCK_LEN = 0x218

    def __init__(self, usb_dev=None):
        LeicaUSB.__init__(self, usb_dev)

        # self.img_queue = gevent.queue.Queue()
        self.last_image = None
        self.new_image = gevent.event.Event()
        self.reader = None
        self.pnb = 1
        atexit.register(self.dev.reset)

    def is_running(self):
        return self.reader is not None

    def start_camera(self):
        if not self.is_running():
            gthreadpool = gevent.get_hub().threadpool
            self.reader = gthreadpool.spawn(self.reader_funct)

    def stop_camera(self):
        if self.is_running():
            t = self.reader
            self.reader = None
            t.join()

    def reader_funct(self):
        self.cfg_ep_out = self.get_end_point(self.CFG_IF_NB, ep_dir=USBDev.EP_OUT)
        self.cfg_ep_in = self.get_end_point(self.CFG_IF_NB, ep_dir=USBDev.EP_IN)
        self.img_ep_in = self.get_end_point(self.IMG_IF_NB, ep_dir=USBDev.EP_IN)
        self.init_camera()
        while self.is_running():
            img = self.read_image()
            if img:
                self.last_image = img
                self.new_image.set()
                self.new_image.clear()
            # if img:
            #    self.img_queue.put(img)
        self.close_camera()

    SPECIAL_STR_ADDR = (
        [0x04, 0x01],
        [0xc4, 0x00, 0x00, 0x00],
        [0x0c, 0x00, 0x00, 0x70],
    )

    def init_camera(self):
        print("Sending magic commands to config interface")

        print("Special Str #0: %s" % self.get_special_str(0))

        self.get_ctrl_data([0xd8, 0x01, 0x00, 0x00], 8)
        self.get_ctrl_data([0x24, 0x00, 0x01, 0x00], 8)
        self.get_ctrl_data([0x18, 0x00, 0x01, 0x00], 4)

        print("Camera Manufacturer: %s" % self.get_manufacturer_str())
        print("Camera Model: %s" % self.get_model_str())
        print("Camera SerialNb: %s" % self.get_serial_nb_str())

        self.get_ctrl_data([0xc4, 0x01, 0x00, 0x00], 8)
        self.get_ctrl_data([0xd0, 0x01, 0x00, 0x00], 8)
        self.get_ctrl_data([0x10, 0x02, 0x00, 0x00], 8)

        print("Reading camera firmware ...")
        self.read_firmware()
        print("  Done!")

        self.get_ctrl_data([0x08, 0x00, 0x00, 0x60], 4)  # image size
        self.get_ctrl_data([0x10, 0x00, 0x00, 0x60], 4)

        print("Special Str #1: %s" % self.get_special_str(1))
        print("Special Str #2: %s" % self.get_special_str(2))

        self.get_ctrl_data([0x88, 0x00, 0x02, 0x90], 4)
        self.get_ctrl_data([0x00, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x00, 0x00, 0x00, 0x82], 0x00000003)
        self.set_ctrl_data([0x00, 0x00, 0x00, 0x82], 0x00000803)
        self.get_ctrl_data([0x00, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x84, 0x00, 0x02, 0x90], 0x00000001)

        self.get_ctrl_data([0x6c, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x70, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x74, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x78, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x7c, 0x02, 0x00, 0x60], 4)

        self.get_ctrl_data([0x18, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x14, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x10, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x34, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x48, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x40, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x3c, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x08, 0x00, 0x00, 0x82], 4)

        self.get_ctrl_data([0xa8, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0xa8, 0x02, 0x00, 0x60], 0x00000000)
        self.set_ctrl_data([0xa8, 0x02, 0x00, 0x60], 0x80000000)
        self.get_ctrl_data([0xa8, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0xa8, 0x02, 0x00, 0x60], 0x00000001)
        self.get_ctrl_data([0xa8, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0xa8, 0x02, 0x00, 0x60], 0x80000001)
        self.get_ctrl_data([0xa8, 0x02, 0x00, 0x60], 4)

        self.get_ctrl_data([0x6c, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x70, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x74, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x78, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x7c, 0x02, 0x00, 0x60], 4)

        self.get_ctrl_data([0xb4, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0xac, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0xb0, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x78, 0x02, 0x00, 0x60], 4)
        self.get_ctrl_data([0x7c, 0x02, 0x00, 0x60], 4)

        self.get_ctrl_data([0x04, 0x00, 0x00, 0x82], 4)

        self.set_ctrl_data([0x04, 0x00, 0x02, 0x00], 0x00000000)
        self.set_ctrl_data([0x10, 0x00, 0x02, 0x00], 0x00000100)
        self.set_ctrl_data([0x24, 0x00, 0x02, 0x00], 0x00000100)

        self.get_ctrl_data([0x00, 0x00, 0x00, 0x00], 4)
        self.get_ctrl_data([0x08, 0x00, 0x02, 0x00], 8)

        self.set_ctrl_data([0x14, 0x00, 0x02, 0x00], 0x00010000)
        self.set_ctrl_data([0x18, 0x00, 0x02, 0x00], 0x00000090)

        self.set_ctrl_data([0x6c, 0x02, 0x00, 0x60], 0xff610800)
        self.set_ctrl_data([0x1c, 0x00, 0x02, 0x00], 0x00000400)
        self.get_ctrl_data([0x6c, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x04, 0x00, 0x02, 0x00], 0x80000000)

        self.set_ctrl_data([0x6c, 0x02, 0x00, 0x60], 0x00000800)
        self.get_ctrl_data([0x6c, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x70, 0x02, 0x00, 0x60], 0xfaa50000)
        self.get_ctrl_data([0x70, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x70, 0x02, 0x00, 0x60], 0x00000000)
        self.get_ctrl_data([0x70, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x74, 0x02, 0x00, 0x60], 0xffe207ff)
        self.get_ctrl_data([0x74, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x74, 0x02, 0x00, 0x60], 0x000007ff)
        self.get_ctrl_data([0x74, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x78, 0x02, 0x00, 0x60], 0xee570000)
        self.get_ctrl_data([0x78, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x78, 0x02, 0x00, 0x60], 0x00000000)
        self.get_ctrl_data([0x78, 0x02, 0x00, 0x60], 4)
        self.set_ctrl_data([0x7c, 0x02, 0x00, 0x60], 0x00000800)
        self.get_ctrl_data([0x7c, 0x02, 0x00, 0x60], 4)
        # ...
        self.get_ctrl_data([0x2c, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x3c, 0x00, 0x00, 0x82], 0x000013db)
        self.set_ctrl_data([0x48, 0x00, 0x00, 0x82], 0x00001487)
        self.get_ctrl_data([0x54, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x54, 0x00, 0x00, 0x82], 0x00000400)
        self.get_ctrl_data([0x24, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x24, 0x00, 0x00, 0x82], 0x00000000)
        self.get_ctrl_data([0x00, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x00, 0x00, 0x00, 0x82], 0x00000801)  # start
        self.get_ctrl_data([0x2c, 0x00, 0x00, 0x82], 4)  # 14 00 18 02

    def close_camera(self):
        print("Sending magic commands to cleanup camera")
        self.get_ctrl_data([0x24, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x24, 0x00, 0x00, 0x82], 0x000001)
        self.get_ctrl_data([0x00, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x00, 0x00, 0x00, 0x82], 0x000803)  # stop
        self.get_ctrl_data([0x3c, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x40, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x48, 0x00, 0x00, 0x82], 4)
        self.get_ctrl_data([0x2c, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x04, 0x00, 0x02, 0x00], 0x000000)
        self.get_ctrl_data([0x24, 0x00, 0x00, 0x82], 4)
        self.set_ctrl_data([0x24, 0x00, 0x00, 0x82], 0x000000)

    def get_manufacturer_str(self):
        return self.get_id_str([0x04, 0x00])

    def get_model_str(self):
        return self.get_id_str([0x44, 0x00])

    def get_serial_nb_str(self):
        return self.get_id_str([0x44, 0x01])

    def get_special_str(self, id):
        return self.get_id_str(self.SPECIAL_STR_ADDR[id])

    def get_id_str(self, addr):
        dlen = 0x20 if addr == [0x0c, 0x00, 0x00, 0x70] else 0x40
        if len(addr) == 2:
            addr += [0x00] * 2
        return self.get_ctrl_data(addr, dlen)

    def read_firmware(self):
        dlen = struct.calcsize(self.FORMAT_18_02)
        s = str(self.get_ctrl_data([0x18, 0x02, 0x00, 0x00], dlen))
        d = struct.unpack(self.FORMAT_18_02, s)
        block = list(d[1:5])
        flen = d[6]
        xfer = 0
        while xfer < flen:
            blen = min(flen - xfer, self.MAX_BLOCK_LEN)
            block[0:2] = xfer & 0xff, (xfer >> 8) & 0xff
            self.get_ctrl_data(block, blen)
            xfer += blen

    def get_ctrl_data(self, addr, dlen):
        ptype = LeicaCamCtrlPacket.TYPE[LeicaCamCtrlPacket.HOST]["Get"]
        rp = LeicaCamCtrlPacket(ptype=ptype, pnb=self.pnb, addr=addr, rlen=dlen)
        # print rp
        self.cfg_ep_out.write(rp.tobytes())
        s = self.cfg_ep_in.read(1024)
        ap = LeicaCamCtrlPacket.frombytes(s)
        # print ap
        ptype = LeicaCamCtrlPacket.TYPE[LeicaCamCtrlPacket.DEV]["Get"]
        if ap.ptype != ptype or ap.pnb != self.pnb or len(ap.rdata) != dlen:
            raise ValueError("Invalid ack packet: %s" % ap)
        self.pnb += 1
        if dlen in [4, 8]:
            return struct.unpack("I" if dlen == 4 else "Q", ap.rdata)
        else:
            slen = ap.rdata.index(0) if dlen == 0x40 else dlen
            return bytearray(ap.rdata[:slen])

    def set_ctrl_data(self, addr, dval):
        ptype = LeicaCamCtrlPacket.TYPE[LeicaCamCtrlPacket.HOST]["Set"]
        rp = LeicaCamCtrlPacket(ptype=ptype, pnb=self.pnb, addr=addr, val=dval)
        # print rp
        self.cfg_ep_out.write(rp.tobytes())
        s = self.cfg_ep_in.read(1024)
        ap = LeicaCamCtrlPacket.frombytes(s)
        # print ap
        ptype = LeicaCamCtrlPacket.TYPE[LeicaCamCtrlPacket.DEV]["Set"]
        if (
            ap.ptype != ptype
            or ap.pnb != self.pnb
            or struct.unpack("I", ap.rdata)[0] != 0x00040000
        ):
            raise ValueError("Invalid ack packet: %s" % ap)
        self.pnb += 1

    def read_image(self):
        p_len = struct.calcsize(LeicaCamImgPacketI.HEADER)
        s = self.img_ep_in.read(p_len)
        p = LeicaCamImgPacketI.frombytes(s)
        image_shape = p.height, p.width, 3
        nb_pixels = image_shape[0] * image_shape[1] + self.EXTRA_PIXELS
        block_size = nb_pixels * image_shape[2]

        align = self.ALIGN
        block_size = int((block_size + align - 1) / align) * align
        data = self.img_ep_in.read(block_size).tostring()

        p_len = struct.calcsize(LeicaCamImgPacketII.HEADER)
        s = self.img_ep_in.read(p_len)
        p = LeicaCamImgPacketII.frombytes(s)
        if p.plen != block_size:
            raise InvalidValue("Image block size mismatch")

        image_size = reduce(lambda a, b: a * b, image_shape)
        isize = image_shape[1], image_shape[0]
        img = ImageRGB(isize, data[:image_size])

        return img

    def get_next_image(self, block=True, timeout=None):
        if not self.is_running():
            self.start_camera()
        if block:
            self.new_image.wait(timeout=timeout)
        return self.last_image
        # return self.img_queue.get(block=block, timeout=timeout)
