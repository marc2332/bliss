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

from bliss.common.event import connect,send
from bliss.config.conductor import client
from bliss.config.settings import Parameters,_change_to_obj_marshalling
from bliss.data.node import _get_or_create_node,_create_node,DataNode
from bliss.session.session import get_default as _default_session
from .chain import AcquisitionDevice, AcquisitionMaster

current_module = sys.modules[__name__]

class StepScanDataWatch(object):
    """
    This class is an helper to follow data generation by a step scan like:
    an acquisition chain with motor(s) as the top-master.
    This produce event compatible with the ScanListener class (bliss.shell)
    """
    def __init__(self,scan_info):
        self._motors = scan_info['motors']
        self._motors_name = [x.name for x in self._motors]
        self._last_point_display = -1
        self._channel_name_2_channel = dict()
        self._scan_info = scan_info
        self._init_done = False

    def __call__(self,data_events,nodes,info):
        if self._init_done is False:
            for acq_device,data_node in nodes.iteritems():
                if data_node.type() == 'zerod':
                    self._channel_name_2_channel.update(
                        ((channel.name,data_node.get_channel(channel.name,check_exists=False)) 
                         for channel in acq_device.channels))
            self._init_done = True

        if self._last_point_display == -1:
            self._last_point_display += 1

        min_nb_points = None
        for channels_name,channel in self._channel_name_2_channel.iteritems():
            nb_points = len(channel)
            if min_nb_points is None:
                min_nb_points = nb_points
            elif min_nb_points > nb_points:
                min_nb_points = nb_points
 
        point_nb = self._last_point_display
        for point_nb in range(self._last_point_display,min_nb_points):
            values = dict([(ch_name, ch.get(point_nb))
                      for ch_name, ch in self._channel_name_2_channel.iteritems()])
            send(current_module,"scan_data",
                 self._scan_info,values)
        if min_nb_points is not None:
            self._last_point_display = min_nb_points


class ScanSaving(Parameters):
    SLOTS = []

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
        Parameters.__init__(self,'%s:scan_data' % self.session,
                            default_values = {'base_path': '/tmp/scans',
                                              'user_name': getpass.getuser(),
                                              'template' : '{session}/',
                                              'date_format': '%Y%m%d' },
                            **keys)

    def __dir__(self) :
        keys = Parameters.__dir__(self)
        return keys + ['session','get','get_path','get_parent_node']

    @property
    def session(self):
        """ This give the name of the default session or unnamed if no default session is defined """
        session = _default_session()
        return session.name if session is not None else 'unnamed'

    @property
    def date(self):
        return time.strftime(self.date_format)

    def get(self):
        """
        This method will compute all configurations needed for a new acquisition.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            parent -- this DataNode should be used as a parent for new acquisition
        """
        try:
            template = self.template
            formatter = string.Formatter()
            cache_dict = self._proxy.get_all()
            cache_dict['session'] = self.session
            cache_dict['date'] = self.date
            template_keys = [key[1] for key in formatter.parse(template)]

            if 'session' in template_keys:
                parent = None
            else:
                parent = _get_or_create_node(self.session,"container")

            for key in template_keys:
                value = cache_dict.get(key)
                if callable(value):
                    value = value(self) # call the function
                    cache_dict[key] = value
                if value is not None:
                    parent = _get_or_create_node(value,"container",
                                                 parent=parent)
            
            sub_path = template.format(**cache_dict)
        except KeyError,keyname:
            raise RuntimeError("Missing %s attribute in ScanSaving" % keyname)
        else:
            return {'root_path' : os.path.join(cache_dict.get('base_path'),sub_path),
                    'parent' : parent}
                    
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

class Container(object):
    def __init__(self, name, parent=None) :
        self.root_node = parent.node if parent is not None else None
        self.__name = name
        self.node = _get_or_create_node(self.__name, "container", parent=self.root_node)

class Scan(object):
    IDLE_STATE,PREPARE_STATE,START_STATE,STOP_STATE = range(4)

    def __init__(self,chain, name=None,
                 parent=None, scan_info=None, writer=None,
                 data_watch_callback=None):
        """
        This class publish data and trig the writer if any.
        
        chain -- acquisition chain you want to use for this scan.
        name -- usually the scan name if None set default name *scan"
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
            if isinstance(parent,DataNode):
                self.root_node = parent
            elif isinstance(parent,Container):
                self.root_node = parent.node         
            else:
                raise ValueError("parent must be a DataNode or Container object, or None")

        self._nodes = dict()
        self._writer = writer

        name = name if name else "scan"

        if parent:
            key = self.root_node.db_name() 
            run_number = client.get_cache(db=1).hincrby(key, "%s_last_run_number" % name, 1)
        else:
            run_number = client.get_cache(db=1).incrby("%s_last_run_number" % name, 1)
	self.__name = '%s_%d' % (name, run_number)
        self._node = _create_node(self.__name, "scan", parent=self.root_node)
        if scan_info is not None:
            scan_info['scan_nb'] = run_number
            scan_info['start_time'] = self._node._data.start_time
            scan_info['start_time_str'] = self._node._data.start_time_str
            scan_info['start_time_stamp'] = self._node._data.start_time_stamp
            self._node._info.update(dict(scan_info))
        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        
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

        self._acq_chain = chain
        self._scan_info = scan_info if scan_info is not None else dict()
        self._scan_info['node_name'] = self._node.db_name()
        self._state = self.IDLE_STATE

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
        
    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == 'end':
            for node in self._nodes.itervalues():
                node.set_ttl()
            self._node.set_ttl()
            self._node.end()
        node = self._nodes[sender]
        if not hasattr(node,'store'): return
        node.store(signal, event_dict)
        
        if self._data_watch_callback is not None:
            event_set = self._data_events.setdefault(sender,set())
            event_set.add(signal)
            if signal == 'end':
                data_events = self._data_events
                self._data_events = dict()
                while self._data_watch_running and not self._data_watch_task.ready():
                    self._data_watch_callback_done.wait()
                    self._data_watch_callback_done.clear()
                self._data_watch_callback(data_events,self.nodes,
                                          {'state':self._state})
            else:
                self._data_watch_callback_event.set()

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

            if isinstance(dev,AcquisitionDevice) or isinstance(dev,AcquisitionMaster):
                self._nodes[dev] = _create_node(dev.name, dev.type, parent_node) 
                for signal in ('start', 'end', 'new_ref','new_data'):
                    connect(dev,signal,self._device_event)

        if self._writer:
            self._writer.prepare(self, scan_info, devices_tree)

    def stop(self):
        for node in self._nodes.itervalues():
            node.set_ttl()
        self._node.set_ttl()
    
    def run(self):
        class _Wakeup(object):
            def __init__(self,cnt,active):
                self.__active = active
                self.__task = None
                self.__cnt = weakref.proxy(cnt)
                
            def __enter__(self):
                if self.__active:
                    self.__task = gevent.spawn(self._timer)

            def __exit__(self,*args):
                if self.__task is not None:
                    gevent.kill(self.__task)
                
            def _timer(self):
                try:
                    while True:
                        self.__cnt._data_watch_callback_event.set()
                        gevent.sleep(0.1)
                except ReferenceError:
                    pass
                
        if hasattr(self._data_watch_callback,'on_state'):
            call_on_prepare = self._data_watch_callback.on_state(self.PREPARE_STATE)
            call_on_stop = self._data_watch_callback.on_state(self.STOP_STATE)
        else:
            call_on_prepare,call_on_stop = False,False

        send(current_module, "scan_new", self.scan_info)
        try:
            i = None
            for i in self.acq_chain:
                self._state = self.PREPARE_STATE
                with _Wakeup(self,call_on_prepare):
                    i.prepare(self,self.scan_info)
                self._state = self.START_STATE
                i.start()
        except:
            self._state = self.STOP_STATE
            with _Wakeup(self,call_on_stop):
                i.stop()
                self.stop()
            raise
        else:
            self._state = self.STOP_STATE
            if i is not None:
                i.stop()
        finally:
            self._state = self.IDLE_STATE
            send(current_module, "scan_end", self.scan_info)

    @staticmethod
    def _data_watch(scan,event,event_done):
        while True:
            event.wait()
            event.clear()
            try:
                data_events = scan._data_events
                scan._data_events = dict()
                scan._data_watch_running = True
                scan._data_watch_callback(data_events,scan.nodes,
                                          {'state':scan._state})
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

        for signal in ('start', 'end', 'new_data'):
            connect(slave, signal, self)

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
                
        for signal in ('start', 'end', 'new_data'):
            connect(device, signal, self)
    
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
    def __init__(self,root_path,
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
        self._root_path = root_path
        self._windows_path_mapping = windows_path_mapping or dict()
        self._detector_temporay_path = detector_temporay_path or dict()
        if None in (master_event_receiver, device_event_receiver):
            raise ValueError("master_event_receiver and device_event_receiver keyword arguments have to be specified.")
        self._master_event_receiver = master_event_receiver
        self._device_event_receiver = device_event_receiver
        self._event_receivers = list()

    def create_path(self, scan_recorder):
        path_suffix = scan_recorder.node.name()
        full_path = os.path.join(self._root_path, path_suffix)
        try:
            os.makedirs(full_path)
        except OSError as exc: # Python >2.5
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
        scan_file_dir = self.create_path(scan_recorder)
        
        self.new_file(scan_file_dir, scan_recorder)

        self._event_receivers = list()

        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                master_entry = self.new_master(dev, scan_file_dir)

                if dev.type == 'lima':
                    try:
                        save_flag = dev.save_flag
                    except AttributeError:
                        save_flag = True

                    parameters  = dev.parameters
                    camera_name = dev.device.camera_type
                    scan_name   = scan_recorder.node.name()
                    full_path = os.path.join(scan_file_dir,dev.device.user_detector_name)

                    parameters.setdefault('saving_mode', 'AUTO_FRAME' if save_flag else 'MANUAL')
                    if save_flag :
                        parameters.setdefault('saving_format', 'EDF')
                        parameters.setdefault('saving_frame_per_file', 1)
                        parameters.setdefault('saving_directory', full_path)
                        parameters.setdefault('saving_prefix', '%s_%s' % (scan_name,camera_name))
                        parameters.setdefault('saving_suffix', '.edf')
                                
                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice):
                        self._event_receivers.append(self._device_event_receiver(slave, master_entry))
                    elif isinstance(slave,AcquisitionMaster):
                        self._event_receivers.append(self._master_event_receiver(slave, slave, master_entry))
                self._event_receivers.append(self._device_event_receiver(dev, master_entry))
