# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import getpass
import gevent
import os
import string
import weakref
import sys
from treelib import Tree
import time
import datetime
import re
import numpy
import collections
import uuid

from bliss import setup_globals
from bliss.common.event import connect, send, disconnect
from bliss.common.cleanup import error_cleanup, axis as cleanup_axis, capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.common.plot import get_flint, CurvePlot, ImagePlot
from bliss.common.utils import periodic_exec, get_axes_positions_iter
from bliss.common.utils import Statistics
from bliss.config.conductor import client
from bliss.config.settings import Parameters, _change_to_obj_marshalling
from bliss.data.node import (
    _get_or_create_node,
    _create_node,
    DataNodeContainer,
    is_zerod,
)
from bliss.data.scan import get_data
from bliss.common.session import get_current as _current_session
from .chain import AcquisitionDevice, AcquisitionMaster
from .writer.null import Writer as NullWriter
from .scan_math import peak, cen, com
from . import writer

# Globals
SCANS = collections.deque(maxlen=20)
current_module = sys.modules[__name__]


class StepScanDataWatch(object):
    """
    This class is an helper to follow data generation by a step scan like:
    an acquisition chain with motor(s) as the top-master.
    This produce event compatible with the ScanListener class (bliss.shell)
    """

    def __init__(self):
        self._last_point_display = 0
        self._channel_name_2_channel = dict()
        self._init_done = False

    def __call__(self, data_events, nodes, scan_info):
        if self._init_done is False:
            for acq_device_or_channel, data_node in nodes.iteritems():
                if is_zerod(data_node):
                    channel = data_node
                    self._channel_name_2_channel[channel.name] = channel
            self._init_done = True

        min_nb_points = None
        for channels_name, channel in self._channel_name_2_channel.iteritems():
            nb_points = len(channel)
            if min_nb_points is None:
                min_nb_points = nb_points
            elif min_nb_points > nb_points:
                min_nb_points = nb_points

        if min_nb_points is None or self._last_point_display >= min_nb_points:
            return

        for point_nb in range(self._last_point_display, min_nb_points):
            values = {
                ch_name: ch.get(point_nb)
                for ch_name, ch in self._channel_name_2_channel.iteritems()
            }
            send(current_module, "scan_data", scan_info, values)
        self._last_point_display = min_nb_points


class ScanSaving(Parameters):
    SLOTS = []
    WRITER_MODULE_PATH = "bliss.scanning.writer"

    def __init__(self, name=None):
        """
        This class hold the saving structure for a session.

        This class generate the *root path* of scans and the *parent* node use to publish data.

        The *root path* is generate using *base path* argument as the first part and
        use the *template* argument as the final part.
        The *template* argument is basically a (python) string format use to generate the final part of the
        root_path.
        i.e: a template like "{session}/{date}" will use the session and the date attribute
        of this class.
        attribute use in this template can also be a function with one argument (scan_data) which return a string.
        i.e: date argument can point to this method
             def get_date(scan_data): datetime.datetime.now().strftime("%Y/%m/%d")
             scan_data.add('date',get_date)

        The *parent* node should be use as parameters for the Scan.
        """

        keys = dict()
        _change_to_obj_marshalling(keys)

        Parameters.__init__(
            self,
            "scan_saving:%s" % name if name else "scan_saving:%s" % uuid.uuid4().hex,
            default_values={
                "base_path": "/tmp/scans",
                "data_filename": "data",
                "user_name": getpass.getuser(),
                "template": "{session}/",
                "images_path_relative": True,
                "images_path_template": "scan{scan_number}",
                "images_prefix": "{img_acq_device}_",
                "date_format": "%Y%m%d",
                "scan_number_format": "%04d",
                "_writer_module": "hdf5",
                "_last_scan_number": 0,
                "_last_scan_file": "",
            },
            **keys
        )

    def __dir__(self):
        keys = Parameters.__dir__(self)
        return keys + ["session", "get", "get_path", "get_parent_node", "writer"]

    def __repr__(self):
        d = self._proxy.get_all()
        d["writer"] = d.get("_writer_module")
        d["session"] = self.session
        d["date"] = self.date
        d["scan_name"] = "scan name"
        d["scan_number"] = "scan number"
        d["img_acq_device"] = "<images_* only> acquisition device name"
        return self._repr(d)

    @property
    def scan_name(self):
        return "{scan_name}"

    @property
    def scan_number(self):
        return "{scan_number}"

    @property
    def img_acq_device(self):
        return "{img_acq_device}"

    @property
    def session(self):
        """ This give the name of the current session or 'default' if no current session is defined """
        session = _current_session()
        return session.name if session is not None else "default"

    @property
    def date(self):
        return time.strftime(self.date_format)

    @property
    def writer(self):
        """
        Scan writer object.
        """
        return self._proxy["_writer_module"]

    @writer.setter
    def writer(self, value):
        try:
            if value is not None:
                self._get_writer_class(value)
        except ImportError, exc:
            raise ImportError(
                "Writer module **%s** does not"
                " exist or cannot be loaded (%s)"
                " possible module are %s" % (value, exc, writer.__all__)
            )
        except AttributeError, exc:
            raise AttributeError(
                "Writer module **%s** does have"
                " class named Writer (%s)" % (value, exc)
            )
        else:
            self._proxy["_writer_module"] = value

    def get(self):
        """
        This method will compute all configurations needed for a new acquisition.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            images_path -- compute images path with *base_path* and *images_path_template* attribute
                If images_path_relative is set to True (default), the path
                template is relative to the scan path, otherwise the
                image_path_template has to be an absolute path.
            parent -- DataNodeContainer to be used as a parent for new acquisition
        """
        try:
            template = self.template
            images_template = self.images_path_template
            images_prefix = self.images_prefix
            data_filename = self.data_filename
            formatter = string.Formatter()
            cache_dict = self._proxy.get_all()
            cache_dict["session"] = self.session
            cache_dict["date"] = self.date
            cache_dict["scan_name"] = self.scan_name
            cache_dict["scan_number"] = self.scan_number
            cache_dict["img_acq_device"] = self.img_acq_device
            writer_module = cache_dict.get("_writer_module")
            template_keys = [key[1] for key in formatter.parse(template)]

            for key in template_keys:
                value = cache_dict.get(key)
                if callable(value):
                    value = value(self)  # call the function
                    cache_dict[key] = value
            sub_path = template.format(**cache_dict)
            images_sub_path = images_template.format(**cache_dict)
            images_prefix = images_prefix.format(**cache_dict)
            data_filename = data_filename.format(**cache_dict)

            parent = _get_or_create_node(self.session, "container")
            sub_items = os.path.normpath(sub_path).split(os.path.sep)
            try:
                if parent.name == sub_items[0]:
                    del sub_items[0]
            except IndexError:
                pass
            for path_item in sub_items:
                parent = _get_or_create_node(path_item, "container", parent=parent)
        except KeyError, keyname:
            raise RuntimeError("Missing %s attribute in ScanSaving" % keyname)
        else:
            path = os.path.join(cache_dict.get("base_path"), sub_path)
            if self.images_path_relative:
                images_path = os.path.join(path, images_sub_path, images_prefix)
            else:
                images_path = os.path.join(images_sub_path, images_prefix)

            return {
                "root_path": path,
                "data_path": os.path.join(path, data_filename),
                "images_path": images_path,
                "parent": parent,
                "writer": self._get_writer_object(path, images_path, data_filename),
            }

    def get_path(self):
        """
        This method return the current saving path.
        The path is compute with *base_path* and follow the *template* attribute
        to generate it.
        """
        return self.get()["root_path"]

    def get_parent_node(self):
        """
        This method return the parent node which should be used to publish new data
        """
        return self.get()["parent"]

    def _get_writer_class(self, writer_module):
        module_name = "%s.%s" % (self.WRITER_MODULE_PATH, writer_module)
        writer_module = __import__(module_name, fromlist=[""])
        return getattr(writer_module, "Writer")

    def _get_writer_object(self, path, images_path, data_filename):
        if self.writer is None:
            return
        klass = self._get_writer_class(self.writer)
        return klass(path, images_path, data_filename)


class ScanDisplay(Parameters):
    SLOTS = []

    def __init__(self):
        """
        This class represents the display parameters for scans for a session.
        """
        keys = dict()
        _change_to_obj_marshalling(keys)
        Parameters.__init__(
            self,
            "%s:scan_display_params" % self.session,
            default_values={"auto": False, "motor_position": True},
            **keys
        )

    def __dir__(self):
        keys = Parameters.__dir__(self)
        return keys + ["session", "auto"]

    @property
    def session(self):
        """ This give the name of the current session or default if no current session is defined """
        session = _current_session()
        return session.name if session is not None else "default"


def _get_channels_dict(acq_object, channels_dict):
    scalars = channels_dict.setdefault("scalars", [])
    spectra = channels_dict.setdefault("spectra", [])
    images = channels_dict.setdefault("images", [])

    for acq_chan in acq_object.channels:
        name = acq_object.name + ":" + acq_chan.name
        shape = acq_chan.shape
        if len(shape) == 0 and not name in scalars:
            scalars.append(name)
        elif len(shape) == 1 and not name in spectra:
            spectra.append(name)
        elif len(shape) == 2 and not name in images:
            images.append(name)

    return channels_dict


def _get_masters_and_channels(acq_chain):
    # go through acq chain, group acq channels by master and data shape
    tree = acq_chain._tree

    chain_dict = dict()
    for path in tree.paths_to_leaves():
        master = None
        # path[0] is root
        for acq_object in path[1:]:
            # it is mandatory to find an acq. master first
            if isinstance(acq_object, AcquisitionMaster):
                if master is None or acq_object.parent is None:
                    master = acq_object.name
                    channels = chain_dict.setdefault(master, {"master": {}})
                    _get_channels_dict(acq_object, channels["master"])
                    continue
            _get_channels_dict(acq_object, channels)
    return chain_dict


def display_motor(func):
    def f(self, *args, **kwargs):
        axis = func(self, *args, **kwargs)
        scan_display_params = ScanDisplay()
        if scan_display_params.auto and scan_display_params.motor_position:
            p = self.get_plot(axis)
            p.qt.addXMarker(axis.position(), legend=axis.name, text=axis.name)

    return f


class Scan(object):
    IDLE_STATE, PREPARE_STATE, START_STATE, STOP_STATE = range(4)

    def __init__(
        self,
        chain,
        name="scan",
        scan_info=None,
        save=True,
        save_images=True,
        scan_saving=None,
        data_watch_callback=None,
    ):
        """
        This class publish data and trig the writer if any.

        chain -- acquisition chain you want to use for this scan.
        name -- scan name, if None set default name *scan*
        parent -- the parent is the root node of the data tree.
        usually the parent is a Container like to a session,sample,experiment...
        i.e: parent = Container('eh3')
        scan_info -- should be the scan parameters as a dict
        writer -- is the final file writer (hdf5,cvs,spec file...)
        data_watch_callback -- a callback which can follow the data status of the scan.
        this callback is usually used to display the scan status.
        the callback will get:
            - data_event : a dict with Acq(Device/Master) as key and a set of signal as values
            - nodes : a dict with Acq(Device/Master) as key and the associated data node as value
            - info : dictionnary which contains the current scan state...
        if the callback is a class and have a method **on_state**, it will be called on each
        scan transition state. The return of this method will activate/deactivate
        the calling of the callback during this stage.
        """
        self.__name = name
        self._scan_info = dict(scan_info) if scan_info is not None else dict()

        if scan_saving is None:
            session_obj = _current_session()
            if session_obj is None:
                scan_saving = ScanSaving("default")
            else:
                scan_saving = session_obj.env_dict["SCAN_SAVING"]
        session_name = scan_saving.session
        user_name = scan_saving.user_name
        self.__scan_saving = scan_saving
        scan_config = scan_saving.get()

        self.root_node = scan_config["parent"]

        self._scan_info["save"] = save
        if save:
            self.__writer = scan_config["writer"]
        else:
            self.__writer = NullWriter()
        self.__writer._save_images = save_images

        ### order is important in the next lines...
        self.writer.template.update(
            {
                "scan_name": self.name,
                "session": session_name,
                "scan_number": "{scan_number}",
            }
        )

        self.__scan_number = self._next_scan_number()

        self.writer.template["scan_number"] = self.scan_number

        self.__nodes = dict()
        self._devices = []

        self._scan_info["session_name"] = session_name
        self._scan_info["user_name"] = user_name
        self._scan_info["scan_nb"] = self.__scan_number
        self._scan_info.setdefault("title", name)
        start_timestamp = time.time()
        start_time = datetime.datetime.fromtimestamp(start_timestamp)
        self._scan_info["start_time"] = start_time
        start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
        self._scan_info["start_time_str"] = start_time_str
        self._scan_info["start_timestamp"] = start_timestamp
        self._scan_info["positioners"] = {}
        self._scan_info["positioners_dial"] = {}
        for axis_name, axis_pos, axis_dial_pos, unit in get_axes_positions_iter(
            on_error="ERR"
        ):
            self._scan_info["positioners"][axis_name] = axis_pos
            self._scan_info["positioners_dial"][axis_name] = axis_dial_pos

        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        self._acq_chain = chain
        self._scan_info["acquisition_chain"] = _get_masters_and_channels(
            self._acq_chain
        )

        scan_display_params = ScanDisplay()
        if scan_display_params.auto:
            get_flint()

        self._state = self.IDLE_STATE
        node_name = str(self.__scan_number) + "_" + self.name
        self.__node = _create_node(
            node_name, "scan", parent=self.root_node, info=self._scan_info
        )

        if data_watch_callback is not None:
            if not callable(data_watch_callback):
                raise TypeError("data_watch_callback needs to be callable")
            data_watch_callback_event = gevent.event.Event()
            data_watch_callback_done = gevent.event.Event()

            def trig(*args):
                data_watch_callback_event.set()

            self._data_watch_running = False
            self._data_watch_task = gevent.spawn(
                Scan._data_watch,
                weakref.proxy(self, trig),
                data_watch_callback_event,
                data_watch_callback_done,
            )
            self._data_watch_callback_event = data_watch_callback_event
            self._data_watch_callback_done = data_watch_callback_done
        else:
            self._data_watch_task = None

    def __repr__(self):
        return "Scan(number={}, name={}, path={})".format(
            self.__scan_number, self.name, self.writer.filename
        )

    @property
    def name(self):
        return self.__name

    @property
    def writer(self):
        return self.__writer

    @property
    def node(self):
        return self.__node

    @property
    def nodes(self):
        return self.__nodes

    @property
    def acq_chain(self):
        return self._acq_chain

    @property
    def scan_info(self):
        return self._scan_info

    @property
    def scan_number(self):
        if self.__scan_number:
            return self.__scan_saving.scan_number_format % self.__scan_number
        else:
            return "{scan_number}"

    @property
    def statistics(self):
        return Statistics(self._acq_chain._statistic_container)

    def _get_x_y_data(self, counter, axis=None):
        acq_chain = self._scan_info["acquisition_chain"]
        master_axes = []
        for top_level_master in acq_chain.keys():
            for scalar_master in acq_chain[top_level_master]["master"]["scalars"]:
                ma = scalar_master.split(":")[-1]
                if ma in self._scan_info["positioners"]:
                    master_axes.append(ma)

        if len(master_axes) == 0:
            if self._scan_info.get("type") == "timescan":
                axis_name = "elapsed_time"
            else:
                raise RuntimeError("No axis detected in scan.")
        else:
            if len(master_axes) > 1 and axis is None:
                raise ValueError(
                    "Multiple axes detected, please provide axis for \
                                 calculation."
                )
            if axis is None:
                axis_name = master_axes[0]
            else:
                axis_name = axis.name
                if axis_name not in master_axes:
                    raise ValueError("No master for axis '%s`." % axis_name)

        data = self.get_data()
        x_data = data[axis_name]
        y_data = data[counter.name]

        return x_data, y_data, axis_name

    def fwhm(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        _, fwhm = cen(x, y)
        return fwhm

    def peak(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return peak(x, y)

    def com(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return com(x, y)

    def cen(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return cen(x, y)

    @display_motor
    def goto_peak(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        pk = self.peak((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(pk)
        return axis

    @display_motor
    def goto_com(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        com_value = self.com((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(com_value)
        return axis

    @display_motor
    def goto_cen(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        cfwhm, _ = self.cen((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(cfwhm)
        return axis

    @display_motor
    def where(self, axis=None):
        if axis is None:
            try:
                acq_chain = self._scan_info["acquisition_chain"]
                for top_level_master in acq_chain.keys():
                    for scalar_master in acq_chain[top_level_master]["master"][
                        "scalars"
                    ]:
                        axis_name = scalar_master.split(":")[-1]
                        if axis_name in self._scan_info["positioners"]:
                            raise StopIteration
            except StopIteration:
                axis = getattr(setup_globals, axis_name)
            else:
                RuntimeError("Can't find axis in this scan")
        return axis

    def __trigger_data_watch_callback(self, signal, sender, sync=False):
        if self._data_watch_callback is not None:
            event_set = self._data_events.setdefault(sender, set())
            event_set.add(signal)
            if sync:
                data_events = self._data_events
                self._data_events = dict()
                while self._data_watch_running and not self._data_watch_task.ready():
                    self._data_watch_callback_done.wait()
                    self._data_watch_callback_done.clear()
                self._scan_info["state"] = self._state
                self._data_watch_callback(data_events, self.nodes, self._scan_info)
            else:
                self._data_watch_callback_event.set()

    def _channel_event(self, event_dict, signal=None, sender=None):
        with KillMask():
            self.nodes[sender].store(event_dict)

        self.__trigger_data_watch_callback(signal, sender)

    def set_ttl(self):
        for node in self.nodes.itervalues():
            node.set_ttl()
        self.node.set_ttl()
        self.node.end()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == "end":
            self.__trigger_data_watch_callback(signal, sender, sync=True)

    def prepare(self, scan_info, devices_tree):
        parent_node = self.node
        prev_level = 1
        self.__nodes = dict()
        self._devices = list(devices_tree.expand_tree(mode=Tree.WIDTH))[1:]

        for dev in self._devices:
            dev_node = devices_tree.get_node(dev)
            level = devices_tree.depth(dev_node)
            if prev_level != level:
                prev_level = level
                parent_node = self.nodes[dev_node.bpointer]

            if isinstance(dev, (AcquisitionDevice, AcquisitionMaster)):
                data_container_node = _create_node(dev.name, parent=parent_node)
                self.nodes[dev] = data_container_node
                for channel in dev.channels:
                    self.nodes[channel] = _get_or_create_node(
                        channel.name,
                        channel.data_node_type,
                        data_container_node,
                        shape=channel.shape,
                        dtype=channel.dtype,
                    )
                    connect(channel, "new_data", self._channel_event)
                for signal in ("start", "end"):
                    connect(dev, signal, self._device_event)

        self.writer.prepare(self)
        self._scan_info["root_path"] = self.writer.root_path

    def disconnect_all(self):
        for dev in self._devices:
            if isinstance(dev, (AcquisitionDevice, AcquisitionMaster)):
                for channel in dev.channels:
                    disconnect(channel, "new_data", self._channel_event)
                for signal in ("start", "end"):
                    disconnect(dev, signal, self._device_event)
        self._devices = []

    def run(self):
        if hasattr(self._data_watch_callback, "on_state"):
            call_on_prepare = self._data_watch_callback.on_state(self.PREPARE_STATE)
            call_on_stop = self._data_watch_callback.on_state(self.STOP_STATE)
        else:
            call_on_prepare, call_on_stop = False, False

        if self._data_watch_callback:
            set_watch_event = self._data_watch_callback_event.set
        else:
            set_watch_event = None

        current_iters = [i.next() for i in self.acq_chain.get_iter_list()]

        try:
            send(current_module, "scan_new", self.scan_info)

            self._state = self.PREPARE_STATE
            with periodic_exec(0.1 if call_on_prepare else 0, set_watch_event):
                self.prepare(self.scan_info, self.acq_chain._tree)
                prepare_tasks = [
                    gevent.spawn(i.prepare, self, self.scan_info) for i in current_iters
                ]
                try:
                    gevent.joinall(prepare_tasks, raise_error=True)
                finally:
                    gevent.killall(prepare_tasks)

            self._state = self.START_STATE
            run_next_tasks = [gevent.spawn(self._run_next, i) for i in current_iters]

            with capture_exceptions(raise_index=0) as capture:
                with capture():
                    try:
                        # The first top_master will end the loop (count=1)
                        gevent.joinall(run_next_tasks, raise_error=True, count=1)
                    finally:
                        gevent.killall(run_next_tasks)

                self._state = self.STOP_STATE

                with periodic_exec(0.1 if call_on_stop else 0, set_watch_event):
                    stop_task = [
                        gevent.spawn(i.stop) for i in current_iters if i is not None
                    ]
                    with capture():
                        try:
                            gevent.joinall(stop_task, raise_error=True)
                        except:
                            with KillMask(masked_kill_nb=1):
                                gevent.joinall(stop_task)
                            gevent.killall(stop_task)
                            raise
        finally:
            self.set_ttl()

            self._state = self.IDLE_STATE

            try:
                send(current_module, "scan_end", self.scan_info)
            finally:
                if self.writer:
                    self.writer.close()
                # Add scan to the globals
                SCANS.append(self)
                # Disconnect events
                self.disconnect_all()
                # Kill data watch task
                if self._data_watch_task is not None:
                    self._data_watch_task.kill()
                # Close nodes
                for node in self.nodes.values():
                    if hasattr(node, "close"):
                        node.close()

    def _run_next(self, next_iter):
        next_iter.start()
        for i in next_iter:
            i.prepare(self, self.scan_info)
            i.start()

    @staticmethod
    def _data_watch(scan, event, event_done):
        while True:
            event.wait()
            event.clear()
            try:
                data_events = scan._data_events
                scan._data_events = dict()
                scan._data_watch_running = True
                scan.scan_info["state"] = scan._state
                scan._data_watch_callback(data_events, scan.nodes, scan.scan_info)
                scan._data_watch_running = False
            except ReferenceError:
                break
            else:
                event_done.set()
                gevent.idle()

    def get_data(self):
        """Return a numpy array with the scan data.

        It is a 1D array corresponding to the scan points.
        Each point is a named structure corresponding to the counter names.
        """
        return get_data(self)

    def _find_plot_type_index(self, scan_item_name, channels):
        channel_name_match = (
            lambda scan_item_name, channel_name: ":" + scan_item_name in channel_name
            or scan_item_name + ":" in channel_name
        )

        scalars = channels.get("scalars", [])
        spectra = channels.get("spectra", [])
        images = channels.get("images", [])

        for i, channel_name in enumerate(scalars):
            if channel_name_match(scan_item_name, channel_name):
                return ("0d", 0)
        for i, channel_name in enumerate(spectra):
            if channel_name_match(scan_item_name, channel_name):
                return ("1d", i)
        for i, channel_name in enumerate(images):
            if channel_name_match(scan_item_name, channel_name):
                return ("2d", i)

        return None

    def get_plot(self, scan_item, wait=False):
        """Return plot object showing 'scan_item' from Flint live scan view

        Argument:
            scan_item: can be a motor, a counter, or anything within a measurement group

        Keyword argument:
            wait (defaults to False): wait for plot to be shown
        """
        for master, channels in self.scan_info["acquisition_chain"].iteritems():
            if scan_item.name == master:
                # return scalar plot(s) with this master
                args = (master, "0d", 0)
                break
            else:
                # find plot within this master slave channels
                args = self._find_plot_type_index(scan_item.name, channels)
                if args is None:
                    # hopefully scan item is one of this master channels
                    args = self._find_plot_type_index(
                        scan_item.name, channels["master"]
                    )
                if args:
                    break
        else:
            raise ValueError("Cannot find plot with '%s`" % scan_item.name)

        plot_type, index = args

        flint = get_flint()
        if wait:
            flint.wait_data(master, plot_type, index)
        plot_id = flint.get_live_scan_plot(master, plot_type, index)
        if plot_type == "0d":
            return CurvePlot(existing_id=plot_id)
        elif plot_type == "1d":
            return CurvePlot(existing_id=plot_id)
        else:
            return ImagePlot(existing_id=plot_id)

    def _next_scan_number(self):
        redis = client.get_cache(db=1)
        filename = self.writer.filename
        last_filename = self.__scan_saving._last_scan_file
        last_scan_number = self.__scan_saving._last_scan_number
        if last_filename != filename:
            self.__scan_saving._last_scan_file = filename
            # find new scan number from existing scans (if any)
            if not "{scan_number}" in filename:
                max_scan_number = 0
                for scan_entry in self.writer.get_scan_entries():
                    try:
                        scan_number = int(scan_entry.split("_")[0])
                    except Exception:
                        continue
                    else:
                        if scan_number > max_scan_number:
                            max_scan_number = scan_number
                last_scan_number = max_scan_number
        scan_number = last_scan_number + 1
        self.__scan_saving._last_scan_number = scan_number
        return scan_number

    @staticmethod
    def trace(on=True):
        """
        Activate logging trace during scan
        """
        self.acq_chain.trace(on)
