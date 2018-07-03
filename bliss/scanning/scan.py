# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import errno
import getpass
import gevent
import os
import string
import weakref
import sys
from treelib import Tree
import time
import logging
import datetime
import re
import peakutils
import math

from bliss import setup_globals
from bliss.common.event import connect, send
from bliss.common.plot import get_flint, CurvePlot, ImagePlot
from bliss.common.utils import periodic_exec, get_axes_positions_iter
from bliss.config.conductor import client
from bliss.config.settings import Parameters, _change_to_obj_marshalling
from bliss.data.node import _get_or_create_node, _create_node, DataNodeContainer, is_zerod
from bliss.data.scan import get_data
from bliss.common.session import get_current as _current_session
from .chain import AcquisitionDevice, AcquisitionMaster
from . import writer

# Globals
SCANS = []
current_module = sys.modules[__name__]


class StepScanDataWatch(object):
    """
    This class is an helper to follow data generation by a step scan like:
    an acquisition chain with motor(s) as the top-master.
    This produce event compatible with the ScanListener class (bliss.shell)
    """

    def __init__(self):
        self._last_point_display = -1
        self._channel_name_2_channel = dict()
        self._init_done = False

    def __call__(self, data_events, nodes, scan_info):
        if self._init_done is False:
            for acq_device_or_channel, data_node in nodes.iteritems():
                if is_zerod(data_node):
                    channel = data_node
                    self._channel_name_2_channel[channel.name] = channel
            self._init_done = True

        if self._last_point_display == -1:
            self._last_point_display += 1

        min_nb_points = None
        for channels_name, channel in self._channel_name_2_channel.iteritems():
            nb_points = len(channel)
            if min_nb_points is None:
                min_nb_points = nb_points
            elif min_nb_points > nb_points:
                min_nb_points = nb_points

        point_nb = self._last_point_display
        for point_nb in range(self._last_point_display, min_nb_points):
            values = dict([(ch_name, ch.get(point_nb))
                           for ch_name, ch in self._channel_name_2_channel.iteritems()])
            send(current_module, "scan_data",
                 scan_info, values)
        if min_nb_points is not None:
            self._last_point_display = min_nb_points


class ScanSaving(Parameters):
    SLOTS = []
    WRITER_MODULE_PATH='bliss.scanning.writer'

    def __init__(self):
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

        Parameters.__init__(self, '%s:scan_data' % self.session,
                            default_values={'base_path': '/tmp/scans',
                                            'user_name': getpass.getuser(),
                                            'template': '{session}/',
                                            'date_format': '%Y%m%d'},
                            **keys)

        cache_dict = self._proxy.get_all()
        if '_writer_module' not in cache_dict:
            #Check if hdf5 is available as a default
            try:
                self._get_writer_object('hdf5', os.getcwd())
            except:
                default_module_name = None
            else:
                default_module_name = 'hdf5'

            self.add('_writer_module', default_module_name)

    def __dir__(self):
        keys = Parameters.__dir__(self)
        return keys + ['session', 'get', 'get_path', 'get_parent_node', 'writer']

    def __repr__(self):
        d = self._proxy.get_all()
        d['writer'] = d.get('_writer_module')
        d['session'] = self.session
        d['date'] = self.date
        return self._repr(d)

    @property
    def session(self):
        """ This give the name of the default session or unnamed if no default session is defined """
        session = _current_session()
        return session.name if session is not None else 'unnamed'

    @property
    def date(self):
        return time.strftime(self.date_format)

    @property
    def writer(self):
        """
        Scan writer object.
        """
        return self._get_writer()

    @writer.setter
    def writer(self, value):
        try:
            if value is not None:
                self._get_writer_object(value, os.getcwd())
        except ImportError, exc:
            raise ImportError('Writer module **%s** does not'
                              ' exist or cannot be loaded (%s)'
                              ' possible module are %s' % (value, exc, writer.__all__))
        except AttributeError, exc:
            raise AttributeError('Writer module **%s** does have'
                                 ' class named Writer (%s)' % (value, exc))
        else:
            self._proxy['_writer_module'] = value

    def get(self):
        """
        This method will compute all configurations needed for a new acquisition.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            parent -- DataNodeContainer to be used as a parent for new acquisition
        """
        try:
            template = self.template
            formatter = string.Formatter()
            cache_dict = self._proxy.get_all()
            cache_dict['session'] = self.session
            cache_dict['date'] = self.date
            writer_module = cache_dict.get('_writer_module')
            template_keys = [key[1] for key in formatter.parse(template)]

            for key in template_keys:
                value = cache_dict.get(key)
                if callable(value):
                    value = value(self)  # call the function
                    cache_dict[key] = value
            sub_path = template.format(**cache_dict)
            parent = _get_or_create_node(self.session, "container")
            for path_item in os.path.normpath(sub_path).split(os.path.sep):
                parent = _get_or_create_node(path_item, "container",
                                             parent=parent)
        except KeyError, keyname:
            raise RuntimeError("Missing %s attribute in ScanSaving" % keyname)
        else:
            path = os.path.join(cache_dict.get('base_path'), sub_path)
            return {'root_path': path,
                    'parent': parent,
                    'writer': self._get_writer_object(writer_module=writer_module,
                                                      path=path)}

    def get_path(self):
        """
        This method return the current saving path.
        The path is compute with *base_path* and follow the *template* attribute
        to generate it.
        """
        return self.get()['root_path']

    def get_parent_node(self):
        """
        This method return the parent node which should be used to publish new data
        """
        return self.get()['parent']

    def _get_writer(self, writer_module=None, path=None):
        if writer_module is None or path is None:
            return self.get()['writer']
        return self._get_writer_object(writer_module, path)

    def _get_writer_object(self, writer_module, path):
        if writer_module is None:
            return None
        module_name = '%s.%s' % (self.WRITER_MODULE_PATH, writer_module)
        writer_module = __import__(module_name, fromlist=[''])
        klass = getattr(writer_module, 'Writer')
        return klass(path)


class ScanDisplay(Parameters):
    SLOTS = []

    def __init__(self):
        """
        This class represents the display parameters for scans for a session.
        """
        keys = dict()
        _change_to_obj_marshalling(keys)
        Parameters.__init__(self, '%s:scan_display_params' % self.session,
                            default_values={ 'auto': False },
                            **keys)

    def __dir__(self):
        keys = Parameters.__dir__(self)
        return keys + ['session', 'auto']

    @property
    def session(self):
        """ This give the name of the default session or unnamed if no default session is defined """
        session = _current_session()
        return session.name if session is not None else 'unnamed'


def _get_channels_dict(acq_object, channels_dict):
    scalars = channels_dict.setdefault('scalars', [])
    spectra = channels_dict.setdefault('spectra', [])
    images = channels_dict.setdefault('images', [])

    for acq_chan in acq_object.channels:
        name = acq_object.name+":"+acq_chan.name
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
        npoints = 0
        master = None
        # path[0] is root
        for acq_object in path[1:]:
            # it is mandatory to find an acq. master first
            if isinstance(acq_object, AcquisitionMaster):
                if master is None or acq_object.npoints != npoints:
                    master = acq_object.name
                    npoints = acq_object.npoints
                    channels = chain_dict.setdefault(master, { "master": {} })
                    _get_channels_dict(acq_object, channels["master"])
                    continue
            _get_channels_dict(acq_object, channels)
    return chain_dict


class Scan(object):
    IDLE_STATE, PREPARE_STATE, START_STATE, STOP_STATE = range(4)

    def __init__(self, chain, name=None,
                 parent=None, scan_info=None, writer=None,
                 data_watch_callback=None, run_number=None, name_suffix=""):
        """
        This class publish data and trig the writer if any.

        chain -- acquisition chain you want to use for this scan.
        name -- scan name, if None set default name *scan"
        parent -- the parent is the root node of the data tree.
        usually the parent is a Container like to a session,sample,experiment...
        i.e: parent = Container('eh3')
        scan_info -- should be the scan parameters as a dict
        writer -- is the final file writter (hdf5,cvs,spec file...)
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
        if parent is None:
            self.root_node = None
        else:
            if isinstance(parent, DataNodeContainer):
                self.root_node = parent
            else:
                raise ValueError(
                    "parent must be a DataNodeContainer object, or None")

        self._nodes = dict()
        self._writer = writer

        name = name if name else "scan"

        if run_number is None:
            run_number = self._next_run_number(name, parent)
        self.__run_number = run_number
        self.__name = '%s_%d%s' % (name, run_number, name_suffix)
        self._scan_info = dict(scan_info) if scan_info is not None else dict()
        self._scan_info['scan_nb'] = run_number
        start_timestamp = time.time()
        start_time = datetime.datetime.fromtimestamp(start_timestamp)
        start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
        self._scan_info['start_time'] = start_time
        self._scan_info['start_time_str'] = start_time_str
        self._scan_info['start_timestamp'] = start_timestamp
        scan_config = ScanSaving()
        if writer is not None:
            self._scan_info['save'] = True
            self._scan_info['root_path'] = writer.root_path
        else:
            self._scan_info['save'] = False
        self._scan_info['session_name'] = scan_config.session
        self._scan_info['user_name'] = scan_config.user_name
        self._scan_info['positioners'] = {}
        self._scan_info['positioners_dial'] = {}
        for axis_name, axis_pos, axis_dial_pos in \
            get_axes_positions_iter(on_error="ERR"):
            self._scan_info['positioners'][axis_name] = axis_pos
            self._scan_info['positioners_dial'][axis_name] = axis_dial_pos

        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        self._acq_chain = chain
        self._scan_info['acquisition_chain'] = _get_masters_and_channels(self._acq_chain)

        scan_display_params = ScanDisplay()
        if scan_display_params.auto:
            get_flint()

        self._state = self.IDLE_STATE
        self._node = _create_node(self.__name, "scan", parent=self.root_node, info=self._scan_info)

        if data_watch_callback is not None:
            if not callable(data_watch_callback):
                raise TypeError("data_watch_callback needs to be callable")
            data_watch_callback_event = gevent.event.Event()
            data_watch_callback_done = gevent.event.Event()

            def trig(*args):
                data_watch_callback_event.set()
            self._data_watch_running = False
            self._data_watch_task = gevent.spawn(Scan._data_watch,
                                                 weakref.proxy(self, trig),
                                                 data_watch_callback_event,
                                                 data_watch_callback_done)
            self._data_watch_callback_event = data_watch_callback_event
            self._data_watch_callback_done = data_watch_callback_done
        else:
            self._data_watch_task = None

    def __repr__(self):
        if not self.path:
            return 'Scan(name={}, run_number={})'.format(
                self.name, self.run_number)
        return 'Scan(name={}, run_number={}, path={})'.format(
            self.name, self.run_number, self.path)

    @property
    def name(self):
        return self.__name

    @property
    def writer(self):
        return self._writer

    @writer.setter
    def writer(self, writer):
        self._writer = writer

    @property
    def node(self):
        return self._node

    @property
    def nodes(self):
        return self._nodes

    @property
    def acq_chain(self):
        return self._acq_chain

    @property
    def scan_info(self):
        return self._scan_info

    @property
    def run_number(self):
        return self.__run_number

    @property
    def path(self):
        return self.scan_info['root_path'] if self.scan_info['save'] else None

    def _get_x_y_data(self, counter, axis=None):
        acq_chain = self._scan_info['acquisition_chain']
        master_axes = []
        for master in acq_chain.keys():
            ma = master.split(':')[-1]
            if ma in self._scan_info['positioners']:
                master_axes.append(ma)

        if len(master_axes) == 0:
            raise RuntimeError("No axis detected in scan.")
        if len(master_axes) > 1 and axis is None:
            raise ValueError("Multiple axes detected, please provide axis for \
                             calculation.")
        if axis is None:
            axis_name = master_axes[0]
        else:
            axis_name = axis.name
            if axis_name not in master_axes:
                raise ValueError("No master for axis '%s`." % axis_name)

        scalars = acq_chain.get(axis_name, {}).get('scalars', [])
        for scalar in scalars:
            if scalar.endswith(counter.name):
                scalar = scalar.split(':')[-1]
                break
        else:
            raise ValueError("No scalar with name '%s`." % counter.name)

        data = self.get_data()
        x_data = data[axis_name]
        y_data = data[scalar]

        return x_data, y_data

    def _peak_gaussian_fit(self, x, y, bkgd_substraction=False, thres=0.3,
                           min_dist=1, width=10):
        """Return gaussian fit params for the peak found in (x,y) data"""
        if bkgd_substraction:
            base = peakutils.baseline(y, 2)
            y -= base

        indexes = peakutils.indexes(y, thres=thres, min_dist=min_dist)

        if len(indexes) > 1:
            raise RuntimeError("Multiple peaks detected, use your own \
                               calculation routine to detect peaks.")

        slice_ = slice(indexes[0] - width, indexes[0] + width + 1)

        amp, cen, sig = peakutils.gaussian_fit(x[slice_], y[slice_],
                                               center_only=False)

        return amp, cen, sig

    def fwhm(self, counter, axis=None, bkgd_substraction=False):
        x, y = self._get_x_y_data(counter, axis)
        amp, cen, sig = self._peak_gaussian_fit(x, y, bkgd_substraction)
        return 2 * sig * (2 * math.log(2)) ** 0.5

    def peak(self, counter, axis=None, bkgd_substraction=False):
        x, y = self._get_x_y_data(counter, axis)
        amp, cen, sig = self._peak_gaussian_fit(x, y, bkgd_substraction)
        return cen

    def com(self, counter, axis=None):
        x, y = self._get_x_y_data(counter, axis)
        return peakutils.peak.centroid(x, y)

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
                self._scan_info['state'] = self._state
                self._data_watch_callback(data_events, self._nodes, self._scan_info)
            else:
                self._data_watch_callback_event.set()

    def _channel_event(self, event_dict, signal=None, sender=None):
        self._nodes[sender].store(event_dict)

        self.__trigger_data_watch_callback(signal, sender)

    def set_ttl(self):
        for node in self._nodes.itervalues():
            node.set_ttl()
        self._node.set_ttl()
        self._node.end()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == 'end':
            self.__trigger_data_watch_callback(signal, sender, sync=True)

    def prepare(self, scan_info, devices_tree):
        parent_node = self._node
        prev_level = 1
        self._nodes = dict()

        for dev in list(devices_tree.expand_tree(mode=Tree.WIDTH))[1:]:
            dev_node = devices_tree.get_node(dev)
            level = devices_tree.depth(dev_node)
            if prev_level != level:
                prev_level = level
                parent_node = self._nodes[dev_node.bpointer]

            if isinstance(dev, (AcquisitionDevice, AcquisitionMaster)):
                data_container_node = _create_node(
                    dev.name, parent=parent_node)
                self._nodes[dev] = data_container_node
                for channel in dev.channels:
                    self._nodes[channel] = _get_or_create_node(channel.name,
                                                               channel.data_node_type,
                                                               data_container_node,
                                                               shape=channel.shape,
                                                               dtype=channel.dtype)
                    connect(channel, 'new_data', self._channel_event)
                for signal in ('start', 'end'):
                    connect(dev, signal, self._device_event)

        if self._writer:
            self._writer.prepare(self, scan_info, devices_tree)

    def run(self):
        if hasattr(self._data_watch_callback, 'on_state'):
            call_on_prepare = self._data_watch_callback.on_state(
                self.PREPARE_STATE)
            call_on_stop = self._data_watch_callback.on_state(self.STOP_STATE)
        else:
            call_on_prepare, call_on_stop = False, False

        send(current_module, "scan_new", self.scan_info)

        if self._data_watch_callback:
            set_watch_event = self._data_watch_callback_event.set
        else:
            set_watch_event = None

        try:
            i = None
            for i in self.acq_chain:
                self._state = self.PREPARE_STATE
                with periodic_exec(0.1 if call_on_prepare else 0, set_watch_event):
                    i.prepare(self, self.scan_info)
                self._state = self.START_STATE
                i.start()
        except BaseException as exc:
            self._state = self.STOP_STATE
            with periodic_exec(0.1 if call_on_stop else 0, set_watch_event):
                if i is not None:
                    i.stop()
            raise
        else:
            self._state = self.STOP_STATE
            if i is not None:
                with periodic_exec(0.1 if call_on_stop else 0, set_watch_event):
                    i.stop()
        finally:
            self.set_ttl()

            self._state = self.IDLE_STATE
            send(current_module, "scan_end", self.scan_info)
            if self._writer:
                self._writer.close()
            # Add scan to the globals
            SCANS.append(self)

    @staticmethod
    def _data_watch(scan, event, event_done):
        while True:
            event.wait()
            event.clear()
            try:
                data_events = scan._data_events
                scan._data_events = dict()
                scan._data_watch_running = True
                scan.scan_info['state'] = scan._state
                scan._data_watch_callback(data_events, scan.nodes,
                                          scan.scan_info)
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

    def get_plot(self, scan_item):
        """Return plot object showing 'scan_item' from Flint live scan view

        scan_item can be a motor, a counter, or anything within a measurement group
        """
        channel_name_match = lambda scan_item_name, channel_name: \
            ':'+scan_item_name in channel_name or scan_item_name+':' in channel_name

        for master, channels in self.scan_info['acquisition_chain'].iteritems():
            scalars = channels.get('scalars', [])
            spectra = channels.get('spectra', [])
            images = channels.get('images', [])

            if scan_item.name == master:
                # return scalar plot(s) with this channel master
                args = (master, '0d', None)
            else:
                for channel_name in scalars:
                    if channel_name_match(scan_item.name, channel_name):
                        args = (master, '0d', 0)
                for i, channel_name in enumerate(spectra):
                    if channel_name_match(scan_item.name, channel_name):
                        args = (master, '1d', i)
                for i, channel_name in enumerate(images):
                    if channel_name_match(scan_item.name, channel_name):
                        args = (master, '2d', i)

        flint = get_flint()
        plot_id = flint.get_live_scan_plot(*args)
        if args[1] == '0d':
            return CurvePlot(existing_id=plot_id)
        elif args[1] == '1d':
            return CurvePlot(existing_id=plot_id)
        else:
            return ImagePlot(existing_id=plot_id)

    def _next_run_number(self, name, parent):
        if parent:
            key = self.root_node.db_name
            cnx = client.get_cache(db=1)
            pipeline = cnx.pipeline()
            pipeline.exists('%s__children_list')
            pipeline.hincrby(key, "%s_last_run_number" % name, 1)
            exist, run_number = pipeline.execute()
            # synchronize with writer
            if not exist and self._writer is not None:
                scan_names = dict()
                match_re = re.compile('(.+?)_(\d+).*')
                for scan_entry in self._writer.get_scan_entries():
                    g = match_re.match(scan_entry)
                    if g:
                        scan_name = g.group(1)
                        run_number = int(g.group(2))
                        previous_run_number = \
                        scan_names.setdefault(scan_name, run_number)
                        if run_number > previous_run_number:
                            scan_names[scan_name] = run_number
                if scan_names:
                    run_number = scan_names.get(name, 0) + 1
                    scan_names[name] = run_number
                    cnx.hmset(key, {"%s_last_run_number" % scan_name:run_number
                                    for scan_name, run_number in scan_names.iteritems()})
        else:
            run_number = client.get_cache(db=1).incrby(
                "%s_last_run_number" % name, 1)
        return run_number

class AcquisitionMasterEventReceiver(object):
    def __init__(self, master, slave, parent):
        self._master = master
        self._parent = parent

        for signal in ('start', 'end'):
            connect(slave, signal, self.on_event)
            for channel in slave.channels:
                connect(channel, 'new_data', self.on_event)
    @property
    def parent(self):
        return self._parent

    @property
    def master(self):
        return self._master

    def on_event(self, event_dict=None, signal=None, sender=None):
        raise NotImplementedError


class AcquisitionDeviceEventReceiver(object):
    def __init__(self, device, parent):
        self._device = device
        self._parent = parent

        for signal in ('start', 'end'):
            connect(device, signal, self.on_event)
            for channel in device.channels:
                connect(channel, 'new_data', self.on_event)

    @property
    def parent(self):
        return self._parent

    @property
    def device(self):
        return self._device

    def on_event(self, event_dict=None, signal=None, sender=None):
        raise NotImplementedError


class FileWriter(object):
    def __init__(self, root_path,
                 windows_path_mapping=None,
                 detector_temporay_path=None,
                 master_event_receiver=None,
                 device_event_receiver=None,
                 **keys):
        """ A default way to organize file structure

        windows_path_mapping -- transform unix path to windows
        i.e: {'/data/visitor/':'Y:/'}
        detector_temporay_path -- temporary path for a detector
        i.e: {detector: {'/data/visitor':'/tmp/data/visitor'}}
        """
        self.log = logging.getLogger(type(self).__name__)
        self._root_path = root_path
        self._windows_path_mapping = windows_path_mapping or dict()
        self._detector_temporay_path = detector_temporay_path or dict()
        if None in (master_event_receiver, device_event_receiver):
            raise ValueError(
                "master_event_receiver and device_event_receiver keyword arguments have to be specified.")
        self._master_event_receiver = master_event_receiver
        self._device_event_receiver = device_event_receiver
        self._event_receivers = list()
        self.closed = True

    @property
    def root_path(self):
        return self._root_path

    def create_path(self, scan_recorder):
        path_suffix = scan_recorder.node.name
        full_path = os.path.join(self._root_path, path_suffix)
        try:
            os.makedirs(full_path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(full_path):
                pass
            else:
                raise
        return full_path

    def new_file(self, scan_file_dir, scan_recorder):
        pass

    def new_master(self, master, scan_file_dir):
        raise NotImplementedError

    def prepare(self, scan_recorder, scan_info, devices_tree):
        if not self.closed:
            self.log.warn(
                'Last write may not have finished correctly. I will cleanup')

        scan_file_dir = self.create_path(scan_recorder)

        self.new_file(scan_file_dir, scan_recorder)

        self._event_receivers = list()

        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                master_entry = self.new_master(dev, scan_file_dir)

                dev.prepare_saving(scan_recorder.node.name, scan_file_dir)

                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice):
                        self._event_receivers.append(
                            self._device_event_receiver(slave, master_entry))
                    elif isinstance(slave, AcquisitionMaster):
                        self._event_receivers.append(
                            self._master_event_receiver(slave, slave, master_entry))
                self._event_receivers.append(
                    self._device_event_receiver(dev, master_entry))
        self._closed = False

    def close(self):
        self.closed = True

    def get_scan_entries(self):
        """
        Should return all scan entries from this path
        """
        return []
