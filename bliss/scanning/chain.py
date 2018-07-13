# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import weakref
import collections
from treelib import Tree

from bliss.common.event import dispatcher
from .channel import AcquisitionChannelList, AcquisitionChannel
from .channel import duplicate_channel


class DeviceIterator(object):
    def __init__(self, device, one_shot):
        self.__device_ref = weakref.ref(device)
        self.__sequence_index = 0
        self._one_shot = one_shot

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.device, name)

    @property
    def device(self):
        return self.__device_ref()

    def next(self):
        if not self._one_shot:
            if not self.device.prepare_once and not self.device.start_once:
                if hasattr(self.__device_ref(), 'wait_reading'):
                    self.__device_ref().wait_reading()
        else:
            raise StopIteration

        self.__sequence_index += 1
        return self

    def _prepare(self):
        if self.__sequence_index > 0 and self.device.prepare_once:
            return
        self.device._prepare()

    def _start(self):
        if self.__sequence_index > 0 and self.device.start_once:
            return
        self.device._start()


class DeviceIteratorWrapper(object):
    def __init__(self, device, one_shot):
        self.__device = weakref.proxy(device)
        self.__iterator = iter(device)
        self.__one_shot = one_shot
        self.next()

    def next(self):
        try:
            self.__current = self.__iterator.next()
        except StopIteration:
            if self.__one_shot:
                raise
            if hasattr(self.__device, 'wait_reading'):
                self.__device.wait_reading()
            self.__iterator = iter(device)
            self.__current = self.__iterator.next()

    def __getattr__(self, name):
        return getattr(self.__current, name)

    @property
    def device(self):
        return self.__current


class ChainPreset(object):
    """
    This class interface will be call by the scan object
    at the beginning and at the end of a scan.

    At typical usage of this class is to manage the opening/closing
    by software or to control beam-line multiplexer(s)
    """
    def get_iterator(self, chain):
        """Yield ChainIterationPreset instances, if needed"""
        pass

    def prepare(self, chain):
        """
        Called on the preparation phase of a scan.
        """
        pass

    def start(self, chain):
        """
        Called on the starting phase of a scan.
        """
        pass

    def stop(self, chain):
        """
        Called at the end of a scan.
        """
        pass


class ChainIterationPreset(object):
    """
    Same usage of the Preset object except that it will be called
    before and at the end of each iteration of the scan.
    """
    def prepare(self):
        """
        Called on the preparation phase of each scan iteration
        """
        pass

    def start(self):
        """
        called on the starting phase of each scan iteration
        """
        pass

    def stop(self):
        """
        Called at the end of each scan iteration
        """
        pass


class AcquisitionMaster(object):
    HARDWARE, SOFTWARE = range(2)

    def __init__(self, device, name, npoints=None, trigger_type=SOFTWARE,
                 prepare_once=False, start_once=False):
        self.__device = device
        self.__name = name
        self.__parent = None
        self.__slaves = list()
        self.__triggers = list()
        self.__channels = AcquisitionChannelList()
        self.__npoints = npoints
        self.__trigger_type = trigger_type
        self.__prepare_once = prepare_once
        self.__start_once = start_once

    @property
    def trigger_type(self):
        return self.__trigger_type

    @property
    def prepare_once(self):
        return self.__prepare_once

    @property
    def start_once(self):
        return self.__start_once

    @property
    def device(self):
        return self.__device

    @property
    def name(self):
        return self.__name

    @property
    def slaves(self):
        return self.__slaves

    @property
    def parent(self):
        return self.__parent

    @parent.setter
    def parent(self, p):
        self.__parent = p

    @property
    def channels(self):
        return self.__channels

    @property
    def npoints(self):
        return self.__npoints

    def _prepare(self):
        for channel in self.channels:
            channel._device_name = self.name

        return self.prepare()

    def prepare(self):
        raise NotImplementedError

    def prepare_image_saving(self, channel_name, directory, prefix):
        pass
    
    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def _start(self):
        dispatcher.send("start", self)
        return_value = self.start()
        return return_value

    def trigger_ready(self):
        return True

    def _trigger(self):
        return self.trigger()

    def trigger(self):
        raise NotImplementedError

    def trigger_slaves(self):
        try:
            if not all([task.ready() for _, task in self.__triggers]):
                invalid_slaves = list()
                for slave, task in self.__triggers:
                    if not task.ready():
                        invalid_slaves.append(slave)
                        task.kill(RuntimeError("%s: Previous trigger is not done, aborting"
                                               % self.name))
                    else:
                        task.kill()
                raise RuntimeError("%s: Aborted due to bad triggering on slaves: %s"
                                   % (self.name, invalid_slaves))
        finally:
            self.__triggers = list()

        for slave in self.slaves:
            if slave.trigger_type == AcquisitionMaster.SOFTWARE:
                self.__triggers.append((slave, gevent.spawn(slave._trigger)))

    def wait_slaves(self):
        gevent.joinall(
            [task for slave, task in self.__triggers], raise_error=True)

    def wait_ready(self):
        # wait until ready for next acquisition
        # (not considering slave devices)
        return True

    def add_external_channel(self, device, name, rename=None, conversion=None,
                             dtype=None):
        """Add a channel from an external source."""
        try:
            source = next(
                channel for channel in device.channels if channel.name == name)
        except StopIteration:
            raise ValueError(
                'The device {} does not have a channel called {}'
                .format(device, name))
        new_channel = duplicate_channel(
            source, name=rename, conversion=conversion, dtype=dtype)
        self.channels.append(new_channel)


class AcquisitionDevice(object):
    HARDWARE, SOFTWARE = range(2)

    def __init__(self, device, name, npoints=0, trigger_type=SOFTWARE,
                 prepare_once=False, start_once=False):
        self.__device = device
        self.__parent = None
        self.__name = name
        self.__trigger_type = trigger_type
        self.__channels = AcquisitionChannelList()
        self.__npoints = npoints
        self.__prepare_once = prepare_once
        self.__start_once = start_once
        self._reading_task = None

    @property
    def parent(self):
        return self.__parent

    @parent.setter
    def parent(self, p):
        self.__parent = p

    @property
    def trigger_type(self):
        return self.__trigger_type

    @property
    def prepare_once(self):
        return self.__prepare_once

    @property
    def start_once(self):
        return self.__start_once

    @property
    def device(self):
        return self.__device

    @property
    def name(self):
        return self.__name

    @property
    def channels(self):
        return self.__channels

    @property
    def npoints(self):
        return self.__npoints

    def _prepare(self):
        for channel in self.channels:
            channel._device_name = self.name

        if not self._check_ready():
            raise RuntimeError(
                "%s: Last reading task is not finished." % self.name)
        return self.prepare()

    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def _start(self):
        self.start()
        self._reading_task = gevent.spawn(self.reading)
        dispatcher.send("start", self)

    def stop(self):
        raise NotImplementedError

    def trigger_ready(self):
        return True

    def _check_ready(self):
        if self._reading_task:
            return self._reading_task.ready()
        return True

    def _trigger(self):
        self.trigger()
        if self._check_ready():
            dispatcher.send("start", self)
            self._reading_task = gevent.spawn(self.reading)

    def trigger(self):
        raise NotImplementedError

    def reading(self):
        pass

    def wait_reading(self):
        return self._reading_task.get() if self._reading_task is not None else True

    def wait_ready(self):
        # wait until ready for next acquisition
        return True


class AcquisitionChainIter(object):
    def __init__(self, acquisition_chain, parallel_prepare=True):
        self.__sequence_index = -1
        self._parallel_prepare = parallel_prepare
        self.__acquisition_chain_ref = weakref.ref(acquisition_chain)
        self._preset_iterators_list = list()
        self._current_preset_iterators_list = list()

        # set all slaves into master
        for master in (x for x in acquisition_chain._tree.expand_tree() if isinstance(x, AcquisitionMaster)):
            del master.slaves[:]
            master.slaves.extend(
                acquisition_chain._tree.get_node(master).fpointer)

        # create iterators tree
        self._tree = Tree()
        self._root_node = self._tree.create_node("acquisition chain", "root")
        device2iter = dict()
        for dev in acquisition_chain._tree.expand_tree():
            if not isinstance(dev, (AcquisitionDevice, AcquisitionMaster)):
                continue
            dev_node = acquisition_chain._tree.get_node(dev)
            one_shot = self.acquisition_chain._device2one_shot_flag.get(dev, True)
            parent = device2iter.get(dev_node.bpointer, "root")
            try:
                it = iter(dev)
            except TypeError:
                dev_iter = DeviceIterator(dev, one_shot)
            else:
                dev_iter = DeviceIteratorWrapper(dev, one_shot)
            device2iter[dev] = dev_iter
            self._tree.create_node(
                tag=dev.name, identifier=dev_iter, parent=parent)

    @property
    def acquisition_chain(self):
        return self.__acquisition_chain_ref()

    def prepare(self, scan, scan_info):
        if self.__sequence_index == 0:
            preset_tasks = list()

            preset_tasks.extend([gevent.spawn(preset.prepare, self.acquisition_chain)
                                 for preset in self.acquisition_chain._presets_list])

            scan.prepare(scan_info, self.acquisition_chain._tree)

            gevent.joinall(preset_tasks, raise_error=True)

            self._preset_iterators_list = list()

            for preset in self.acquisition_chain._presets_list:
                iterator = preset.get_iterator(self.acquisition_chain)
                if isinstance(iterator, collections.Iterable):
                    self._preset_iterators_list.append(iterator)

        self._current_preset_iterators_list = list()
        preset_iterators_tasks = list()
        for iterator in list(self._preset_iterators_list):
            try:
                preset = iterator.next()
                assert isinstance(preset, ChainIterationPreset)
            except StopIteration:
                self._preset_iterators_list.remove(iterator)
            except:
                sys.excepthook(*sys.exc_info())
                self._preset_iterators_list.remove(iterator)
            else:
                self._current_preset_iterators_list.append(preset)
                preset_iterators_tasks.append(gevent.spawn(preset.prepare))

        self._execute(
            "_prepare", wait_between_levels=not self._parallel_prepare)

        gevent.joinall(preset_iterators_tasks, raise_error=True)

    def start(self):
        preset_tasks = list()
        if self.__sequence_index == 0:
            preset_tasks = [gevent.spawn(preset.start, self.acquisition_chain)
                            for preset in self.acquisition_chain._presets_list]

        preset_tasks.extend([gevent.spawn(i.start)
                             for i in self._current_preset_iterators_list])
        gevent.joinall(preset_tasks, raise_error=True)
        self._execute("_start")

    def wait_all_devices(self):
        for acq_dev_iter in (x for x in self._tree.expand_tree() if x is not 'root' and
                             isinstance(x.device, (AcquisitionDevice, AcquisitionMaster))):
            if hasattr(acq_dev_iter, 'wait_reading'):
                acq_dev_iter.wait_reading()
            dispatcher.send("end", acq_dev_iter.device)

    def stop(self):
        try:
            self._execute("stop", master_to_slave=True, wait_all_tasks=True)
            self.wait_all_devices()
        finally:
            preset_tasks = [gevent.spawn(preset.stop, self.acquisition_chain)
                            for preset in self.acquisition_chain._presets_list]
            preset_tasks.extend([gevent.spawn(i.stop)
                                 for i in self._current_preset_iterators_list])

            gevent.joinall(preset_tasks)  # wait to call all stop on preset
            gevent.joinall(preset_tasks, raise_error=True)

    def next(self):
        self.__sequence_index += 1
        gevent.joinall([gevent.spawn(dev_iter.wait_ready) for dev_iter in self._tree.expand_tree()
                        if dev_iter is not 'root'],
                       raise_error=True)
        try:
            if self.__sequence_index:
                for dev_iter in self._tree.expand_tree():
                    if dev_iter is 'root':
                        continue
                    dev_iter.next()
            preset_tasks = [gevent.spawn(i.stop)
                            for i in self._current_preset_iterators_list]
            gevent.joinall(preset_tasks)
            gevent.joinall(preset_tasks, raise_error=True)
        except StopIteration:                # should we stop all devices?
            self.wait_all_devices()
            raise
        return self

    def _execute(self, func_name,
                 master_to_slave=False, wait_between_levels=True,
                 wait_all_tasks=False):
        tasks = list()

        prev_level = None

        if master_to_slave:
            devs = list(self._tree.expand_tree(mode=Tree.WIDTH))[1:]
        else:
            devs = reversed(list(self._tree.expand_tree(mode=Tree.WIDTH))[1:])

        for dev in devs:
            node = self._tree.get_node(dev)
            level = self._tree.depth(node)
            if wait_between_levels and prev_level != level:
                gevent.joinall(tasks, raise_error=True)
                tasks = list()
                prev_level = level
            func = getattr(dev, func_name)
            tasks.append(gevent.spawn(func))
        # ensure that all tasks are executed
        # (i.e: don't raise the first exception on stop)
        if wait_all_tasks:
            gevent.joinall(tasks)

        gevent.joinall(tasks, raise_error=True)


class AcquisitionChain(object):
    def __init__(self, parallel_prepare=False):
        self._tree = Tree()
        self._root_node = self._tree.create_node("acquisition chain", "root")
        self._device_to_node = dict()
        self._presets_list = list()
        self._parallel_prepare = parallel_prepare
        self._device2one_shot_flag = weakref.WeakKeyDictionary()

    @property
    def nodes_list(self):
        nodes_gen = self._tree.expand_tree()
        nodes_gen.next()  # first node is 'root'
        return list(nodes_gen)

    def add(self, master, slave):
        self._device2one_shot_flag.setdefault(slave, False)

        slave_node = self._tree.get_node(slave)
        master_node = self._tree.get_node(master)
        if slave_node is not None and isinstance(slave, AcquisitionDevice):
            if(slave_node.bpointer is not self._root_node and
               master_node is not slave_node.bpointer):
                raise RuntimeError("Cannot add acquisition device %s to multiple masters, current master is %s" % (
                    slave, slave_node._bpointer))
            else:                 # user error, multiple add, ignore for now
                return

        if master_node is None:
            master_node = self._tree.create_node(
                tag=master.name, identifier=master, parent="root")
        if slave_node is None:
            slave_node = self._tree.create_node(
                tag=slave.name, identifier=slave, parent=master)
        else:
            self._tree.move_node(slave, master)
        slave.parent = master

    def add_preset(self, preset):
        """
        Add a preset for the scan.

        Args:
            preset should be inherited for class Preset
        """
        if not isinstance(preset, ChainPreset):
            raise ValueError("Expected ChainPreset instance")
        self._presets_list.append(preset)

    def set_stopper(self, device, stop_flag):
        """
        By default any top master device will stop the scan.
        In case of several top master, you can define which one won't
        stop the scan
        """
        self._device2one_shot_flag[device] = not stop_flag

    def __iter__(self):
        if len(self._tree) > 1:
            return AcquisitionChainIter(self, parallel_prepare=self._parallel_prepare)
        else:
            return iter(())
