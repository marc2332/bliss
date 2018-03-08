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

from bliss.common.event import connect, send
from bliss.common.utils import periodic_exec
from bliss.config.conductor import client
from bliss.config.settings import Parameters, _change_to_obj_marshalling
from bliss.data.node import _get_or_create_node, _create_node, DataNodeContainer, is_zerod
from bliss.common.session import get_current as _current_session
from .chain import AcquisitionDevice, AcquisitionMaster
from . import writer

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

            if 'session' in template_keys:
                parent = None
            else:
                parent = _get_or_create_node(self.session, "container")

            for key in template_keys:
                value = cache_dict.get(key)
                if callable(value):
                    value = value(self)  # call the function
                    cache_dict[key] = value
            sub_path = template.format(**cache_dict)
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
                 data_watch_callback=None):
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

        if parent:
            key = self.root_node.db_name
            run_number = client.get_cache(db=1).hincrby(
                key, "%s_last_run_number" % name, 1)
        else:
            run_number = client.get_cache(db=1).incrby(
                "%s_last_run_number" % name, 1)
        self.__name = '%s_%d' % (name, run_number)
        self._scan_info = dict(scan_info) if scan_info is not None else dict()
        self._scan_info['scan_nb'] = run_number
        start_timestamp = time.time()
        start_time = datetime.datetime.fromtimestamp(start_timestamp)
        start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
        self._scan_info['start_time'] = start_time
        self._scan_info['start_time_str'] = start_time_str
        self._scan_info['start_timestamp'] = start_timestamp
        scan_config = ScanSaving()
        self._scan_info['save'] = writer is not None
        self._scan_info['root_path'] = scan_config.get()['root_path']
        self._scan_info['session_name'] = scan_config.session
        self._scan_info['user_name'] = scan_config.user_name

        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        self._acq_chain = chain

        for i, m in enumerate(scan_info.get("motors", [])):
            self._scan_info['motors'][i] = m.name
        self._scan_info['counters'] = list()
        self._scan_info['other_counters'] = list()
        self._scan_info['acquisition_chain'] = _get_masters_and_channels(self._acq_chain)

        for acq_object in self._acq_chain.nodes_list:
            for acq_chan in acq_object.channels:
                if len(acq_chan.shape) == 0:
                    self._scan_info['counters'].append(acq_chan.name)
                else:
                    self._scan_info['other_counters'].append(acq_chan.name)

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
                self._data_watch_callback(data_events, self._nodes,
                                          {'state': self._state})
            else:
                self._data_watch_callback_event.set()

    def _channel_event(self, event_dict, signal=None, sender=None):
        node = self._nodes[sender]

        node.store(signal, event_dict)

        self.__trigger_data_watch_callback(signal, sender)

    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == 'end':
            for node in self._nodes.itervalues():
                node.set_ttl()
            self._node.set_ttl()
            self._node.end()

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
                    self._nodes[channel] = channel.data_node(
                        data_container_node)
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
            self._state = self.IDLE_STATE
            send(current_module, "scan_end", self.scan_info)
            if self._writer:
                self._writer.close()

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


class AcquisitionMasterEventReceiver(object):
    def __init__(self, master, slave, parent):
        self._master = master
        self._parent = parent

        for signal in ('start', 'end'):
            connect(slave, signal, self)
            for channel in slave.channels:
                connect(channel, 'new_data', self)
    @property
    def parent(self):
        return self._parent

    @property
    def master(self):
        return self._master

    def __call__(self, event_dict=None, signal=None, sender=None):
        return self.on_event(event_dict, signal, sender)

    def on_event(self, event_dict, signal, slave):
        raise NotImplementedError


class AcquisitionDeviceEventReceiver(object):
    def __init__(self, device, parent):
        self._device = device
        self._parent = parent

        for signal in ('start', 'end'):
            connect(device, signal, self)
            for channel in device.channels:
                connect(channel, 'new_data', self)

    @property
    def parent(self):
        return self._parent

    @property
    def device(self):
        return self._device

    def __call__(self, event_dict=None, signal=None, sender=None):
        return self.on_event(event_dict, signal, sender)

    def on_event(self, event_dict, signal, device):
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
