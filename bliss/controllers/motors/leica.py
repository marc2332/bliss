from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.common import log
from bliss.common import event
import atexit
import usb
import sys
import time
import math
import array
import select
import gevent
import gevent.event
import gevent.queue
import gevent.select
from ctypes import cast, c_int, c_uint16, c_short, c_ulong, c_ubyte, c_void_p, \
    POINTER, pointer, py_object, byref, addressof, Structure, CDLL, CFUNCTYPE

libc = CDLL('libc.so.6')
libc.free.argtypes = [c_void_p]

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

    #static void libusb_fill_bulk_transfer 	(
    #		struct libusb_transfer *  	transfer,
    #		libusb_device_handle *  	dev_handle,
    #		unsigned char		  	endpoint,
    #		unsigned char *  		buffer,
    #		int 			 	length,
    #		libusb_transfer_cb_fn 	 	callback,
    #		void * 				user_data,
    #		unsigned int 		 	timeout
    #	)

    def libusb_fill_bulk_transfer(_libusb_transfer_p, dev_handle, endpoint,
                                  buffer, length, callback, user_data, timeout):
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
        _fields_ = [('fd', c_int),
                    ('events', c_uint16)]
    lib._libusb_pollfd = _libusb_pollfd

    # struct libusb_pollfd** libusb_get_pollfds(libusb_context *ctx)
    lib.libusb_get_pollfds.argtypes = [c_void_p]
    lib.libusb_get_pollfds.restype = POINTER(POINTER(_libusb_pollfd))

    # typedef void(*libusb_pollfd_added_cb)(int fd, short events,
    #					    void *user_data)
    lib._libusb_pollfd_added_cb_fn_p = CFUNCTYPE(None, c_int, c_short,
                                                 py_object)
    # typedef void(*libusb_pollfd_removed_cb)(int fd, void *user_data)
    lib._libusb_pollfd_removed_cb_fn_p =  CFUNCTYPE(None, c_int, py_object)

    # void libusb_set_pollfd_notifiers 	(
    #		libusb_context *	  	ctx,
    #		libusb_pollfd_added_cb  	added_cb,
    #		libusb_pollfd_removed_cb  	removed_cb,
    #		void *  	user_data
    #	)
    lib.libusb_set_pollfd_notifiers.argtypes = [c_void_p,
                                            lib._libusb_pollfd_added_cb_fn_p,
                                            lib._libusb_pollfd_removed_cb_fn_p,
                                            py_object]

class _BulkTransferHandler(object):

    def __init__(self, dev, dev_handle, ep, buff, timeout):
        cntx = dev._ctx
        self.lib = cntx.backend
        if self.lib.__module__ != 'usb.backend.libusb1':
            raise NotImplementedError, 'Only libusb1 backend supported'

        self.libusb = sys.modules[self.lib.__module__]
        if _lib is None:
            update_libusb_globals(self.libusb)

        address, length = buff.buffer_info()
        self.transfer = _lib.libusb_alloc_transfer(0)
        _lib.libusb_fill_bulk_transfer(self.transfer,
                                       dev_handle.handle,
                                       ep,
                                       cast(address, POINTER(c_ubyte)),
                                       length,
                                       _libusb_transfer_cb_fn_p(),
                                       None,
                                       timeout)

    def __del__(self):
        _lib.libusb_free_transfer(self.transfer)

    def submit(self, loop):
        done_event = loop.submit(self.transfer)
        done_event.wait()

        if self.transfer.contents.status == LIBUSB_TRANSFER_COMPLETED:
            ret = self.transfer.contents.actual_length
        else:
            status = int(self.transfer.contents.status)
            raise usb.USBError(_str_transfer_error[status],
                               status,
                               _transfer_errno[status])
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
        get_timeout = getattr(self.dev, '_Device__get_timeout')
        transfer = _BulkTransferHandler(self.dev, self.cntx.handle,
                                        ep.bEndpointAddress, buff,
                                        get_timeout(timeout))
        ret = transfer.submit(self.loop)
        return ret

    def read(self, size_or_buffer, timeout=None):
        intf, ep = self.cntx.setup_request(self.dev, self.ep)
        if isinstance(size_or_buffer, array.array):
            buff = size_or_buffer
        else:
            buff = usb.util.create_buffer(size_or_buffer)

        get_timeout = getattr(self.dev, '_Device__get_timeout')
        transfer = _BulkTransferHandler(self.dev, self.cntx.handle,
                                        ep.bEndpointAddress, buff,
                                        get_timeout(timeout))
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
                raise ValueError, 'Must provide either usb_dev or vendor/product'
            usb_dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
            if usb_dev is None:
                raise RuntimeError, ('Could not find USB device %04x:%04x' %
                                     (vendor_id, product_id))
        self.dev = usb_dev
        self.dev.set_configuration()
        self.cfg = self.dev.get_active_configuration()

    def __del__(self):
        if self.loop:
            self.loop.stop()

    def reset(self):
        self.dev.reset()

    def get_end_point(self, iface_nb, ep_nb=None, ep_dir=None, ep_type=None,
                      green=True):
        def match(e):
            if (ep_nb is not None and
                usb.util.endpoint_address(e.bEndpointAddress) != ep_nb):
                return False
            if (ep_dir is not None and
                usb.util.endpoint_direction(e.bEndpointAddress) != ep_dir):
                return False
            if (ep_type is not None and
                usb.util.endpoint_type(e.bmAttributes) != ep_type):
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
            raise NotImplementedError, 'Only Bulk endpoints are gevent-friendly'

    def clear_halt(self, end_point):
        try:
            raw_endpoint = end_point.raw_endpoint
        except AttributeError:
            raw_endpoint = end_point
        self.dev.clear_halt(raw_endpoint)


class LeicaUSB(object):

    VENDOR_ID = 0x1711

    def __init__(self, usb_dev=None, vendor_id=None, product_id=None,
                 reset=False, green=True):
        if vendor_id is None:
            vendor_id = self.VENDOR_ID
        if product_id is None:
            product_id = self.PRODUCT_ID
        self.dev = USBDev(usb_dev, vendor_id, product_id)
        if reset:
            self.dev.reset()
        self.green = green

    def get_end_point(self, iface_nb, ep_nb=None, ep_dir=None, ep_type=None,
                      green=None):
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

    Motors = [('LED_Int', 37),
              ('Mot_38', 38),
              ('Zoom_Mag', 60),
              ('Iris', 62),
              ('Focus_Coarse', 70),
              ('Focus_Fine', 72),
              ('Mot_81', 81),
              ('Mot_83', 83),
              ('Zoom_Mag_10', 160),
              ('Mot_162', 162),
              ('Mot_164', 164),
              ('Mot_166', 166),
              ('Mot_168', 168),
              ('Mot_170', 170),
              ('Mot_172', 172)]
    locals().update(dict(Motors))

    Zoom_Group = [Zoom_Mag, Zoom_Mag_10, Mot_162]
    Non_Status_Group = [Mot_81, Mot_83, Mot_164, Mot_166, Mot_168, Mot_170,
                        Mot_172]
    ALL_MOTORS = 254
    ALL_MOTORS_LINES = len(Motors) + 1 # 70_34

    #Steps = {LED_Int: 0.1,
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
    MOT_STA_MOV  = (1 << 5)
    MOT_STA_LIMN = (1 << 6)
    MOT_STA_LIMP = (1 << 7)

    Cmd = {USBDev.EP_OUT: {MOT_REQ_PST: 'Req.PSt',
                           MOT_REQ_MVA: 'Req.MvA',
                           MOT_REQ_MVR: 'Req.MvR',
                           MOT_REQ_POS: 'Req.Pos'},
           USBDev.EP_IN: {MOT_RES_POS: 'Res.Pos',
                          MOT_RES_STA: 'Res.Sta'}}

    Sta = {MOT_STA_MOV: 'Moving',
           MOT_STA_LIMN: 'Lim-',
           MOT_STA_LIMP: 'Lim+'}

    def __init__(self, usb_dev=None):
        LeicaUSB.__init__(self, usb_dev, reset=True)

        ep_type = USBDev.EP_BULK
        self.ep_out = self.get_end_point(self.CDC_IF_NB, ep_type=ep_type,
                                         ep_dir=USBDev.EP_OUT)
        self.clear_halt(self.ep_out)
        self.ep_in = self.get_end_point(self.CDC_IF_NB, ep_type=ep_type,
                                        ep_dir=USBDev.EP_IN)
        self.clear_halt(self.ep_in)

        self.mne = {}
        self.dial = {}
        self.status = {}
        self.closed = False

        for mne, num in self.Motors:
            self.mne[num] = mne
            self.dial[num] = None
            self.status[num] = None
            #if num not in self.Steps:
            #    self.Steps[num] = 1

        for b in range(16):
            i = 1 << b
            if i not in self.Sta:
                self.Sta[i] = 'Sta.UK%X' % b

        self.nb_req = 1

        self.curr_move = None
        self.close()

        self.write(69, self.Mot_81, 410, 411)
        resp = self.read()
        if resp:
            l = map(int, resp.split())
            if l[:4] != [self.Mot_81, 69, 410, 411]:
                raise RuntimeError, 'Invalid resp'
        else:
            raise RuntimeError, 'No resp'

        res = self.get_all_mot_pos_status()
        for mne, num in self.Motors:
            pos, status = res[num]
            stat = self.get_status_str(status)
            #print "%13s %10s %s" % (mne + ':', pos, stat)

    def close(self):
        if not self.closed:
            try:
                if self.curr_move:
                    self.curr_move.wait()

                if self.nb_req % 2 == 1:
                    print 'Balancing Focus USB requests'
                    self.read_mot_pos(self.Iris)
                self.closed = True
            except:
                pass

    def __del__(self):
        self.close()

    def get_all_mot_pos_status(self):
        res = {}
        all_pos = self.read_all_mot_pos()
        for mne, num in self.Motors:
            if num in self.Zoom_Group[1:]:
                continue
            for anum, pos, status in self.read_mot_pos_status(num):
                res[anum] = (pos, status)
        return res

    def read_all_mot_pos(self, fromcache=False):
        if not fromcache or None in self.dial.values():
            self.write(self.MOT_REQ_POS, self.ALL_MOTORS)
            resp = self.read(multiline=self.ALL_MOTORS_LINES)
            for l in resp:
                fnum, cmd, dial = map(float, l.split())
                num = int(fnum)
                if cmd == self.MOT_RES_POS:
                    self.dial[num] = dial
                    #print num, dial
        pos = dict([(num, dial)
                    for num, dial in self.dial.items()])
        return pos

    def read_mot_pos(self, num, fromcache=False):
        if not fromcache or self.dial[num] is None:
            self.write(self.MOT_REQ_POS, num)
            resp = self.read()
            fnum, cmd, dial = map(float, resp.split())
            if cmd != self.MOT_RES_POS:
                raise RuntimeError, 'Invalid MOT_RES_POS: %s' % resp
            num = int(fnum)
            self.dial[int(num)] = dial
        return dial #self.calc_mot_pos(num, dial)

    def read_mot_pos_status(self, num):
        if num in self.Non_Status_Group:
            pos = self.dial[num] #self.calc_mot_pos(num, self.dial[num])
            return [[num, pos, 0]]
        self.write(self.MOT_REQ_PST, num)
        real_mot = [num]
        lines = 2
        zoom_group = num in self.Zoom_Group
        if zoom_group:
            real_mot = self.Zoom_Group
            lines = 2 * len(real_mot) + 1 # 70_34
        resp = self.read(multiline=lines)
        data = [map(float, l.split()) for l in resp]
        res = [([0] * 3) for i in xrange(len(real_mot))]
        for fnum, cmd, val in data:
            num = int(fnum)
            if cmd not in [self.MOT_RES_STA, self.MOT_RES_POS]:
                continue
            k = real_mot.index(num)
            res[k][0] = num
            if cmd == self.MOT_RES_POS:
                self.dial[num] = val
                res[k][1] = self.dial[num] #self.calc_mot_pos(num, self.dial[num])
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
            return 'Idle'
        return ','.join([n for b, n in self.Sta.items() if status & b != 0])

    def start_mot_move(self, num, pos, rel):
        #if self.curr_move:
        #    self.curr_move.wait()
        cmd = self.MOT_REQ_MVR if rel else self.MOT_REQ_MVA
        dial = pos #self.calc_mot_dial(num, pos)
        self.write(cmd, num, dial)
        #gevent.spawn(self.read, multiline=True) #res = self.read(multiline=True)
        self.curr_move = gevent.spawn(self.read, multiline=True)
        #print "res=%s" % res
        #self.curr_move = gevent.spawn(self.poll_mot_move, num)
        #return self.curr_move

    #def poll_mot_move(self, num):
    #    while True:
    #        for anum, pos, status in self.read_mot_pos_status(num):
    #            if status & self.MOT_STA_MOV:
    #                break
    #        else:
    #            break
    #    #print "Finished move"

    def write(self, cmd, mot, *args):
        s = ' '.join(map(lambda x: '%d' % x, [mot, cmd] + list(args)))
        #print 'Write: %s' % s
        self.ep_out.write(s + '\r')
        self.nb_req += 1

    def read(self, multiline=False):
        res = []
        while type(multiline) is bool or len(res) < multiline:
            try:
                s = bytearray(self.ep_in.read(1024)).strip()
                s = s.split('\r\n')[0]
                if multiline is False:
                    #print 'Read: %s' % s
                    return s
                if s not in res:
                    res.append(s)
            except:
                #raise
                break
        #for i, s in enumerate(res):
        #    print "Read+ [%d]: '%s'" % (i, s)
        #    pass
        return res


class leica(Controller):

    def __init__(self, name, config, axes, encoders):
        Controller.__init__(self, name, config, axes, encoders)

        self.usb_controller = None

    def __del__(self):
        try:
            self.usb_controller.close()
        except Exception:
            sys.excepthook(*sys.exc_info())

    def initialize(self):
        try:
            self.usb_controller = LeicaFocus()
        except Exception:
            sys.excepthook(*sys.exc_info())
            raise RuntimeError("Could not initialize Leica controller (hint: is microscope switched on ? Or try to re-plug USB)")

    def finalize(self):
        if self.usb_controller:
            self.usb_controller.close()

    def initialize_axis(self, axis):
        pass

    def read_position(self, axis):
        mot_num = axis.config.get("channel",int)
        if self.state(axis)=='MOVING':
            return 0
        return self.usb_controller.read_mot_pos(mot_num)

    def state(self, axis):
        mot_num = axis.config.get("channel",int)
        #print 'calling state for',mot_num
        if self.usb_controller.curr_move and not self.usb_controller.curr_move.ready():
            return AxisState("MOVING")
        mot_group = self.usb_controller.read_mot_pos_status(mot_num)
        for mot, pos, state in mot_group:
            if mot == mot_num:
                if state & self.usb_controller.MOT_STA_MOV:
                    return AxisState("MOVING")
                elif state & self.usb_controller.MOT_STA_LIMN:
                    return AxisState("READY", "LIMNEG")
                elif state & self.usb_controller.MOT_STA_LIMP:
                    return AxisState("READY", "LIMPOS")
                else:
                    return AxisState("READY")

    def stop(self, axis):
        pass

    def start_one(self, motion):
        axis = motion.axis
        mot_num = axis.config.get("channel",int)
        self.usb_controller.start_mot_move(mot_num, motion.target_pos, False)
