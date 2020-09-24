# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import sys
import logging
import weakref
import enum
import collections
from contextlib import contextmanager

import gevent
from treelib import Tree

from bliss.common.event import dispatcher
from bliss.common.alias import CounterAlias
from bliss.common.cleanup import capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.scanning.channel import AcquisitionChannelList, AcquisitionChannel
from bliss.scanning.channel import duplicate_channel, attach_channels
from bliss.common.validator import BlissValidator
from bliss.common.profiling import time_profile


TRIGGER_MODE_ENUM = enum.IntEnum("TriggerMode", "HARDWARE SOFTWARE")


# Running task for a specific device
#
_running_task_on_device = weakref.WeakValueDictionary()
_logger = logging.getLogger("bliss.scans")


# Used to stop a greenlet and avoid logging this exception
class StopTask(gevent.GreenletExit):
    pass


# Normal chain stop
class StopChain(StopTask):
    pass


@contextmanager
def profile(stats_dict, device_name, func_name):
    name = f"{device_name}.{func_name}"
    try:
        with time_profile(stats_dict, name, logger=_logger):
            yield
    except StopTask:
        raise
    except BaseException as e:
        msg = str(e)
        if not msg:
            msg = type(e).__name__
        _logger.error(f"Exception caught in {name} ({msg})")
        raise


def join_tasks(greenlets, **kw):
    try:
        gevent.joinall(greenlets, raise_error=True, **kw)
    except StopTask as e:
        gevent.killall(greenlets, exception=type(e))
        raise
    except BaseException:
        gevent.killall(greenlets)
        raise


class AbstractDeviceIterator:
    def __init__(self):
        self._stats_dict = dict()  # will be set by `_prepare`

    @property
    def device(self):
        raise NotImplementedError

    def __next__(self):
        raise NotImplementedError

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.device, name)

    def _wait_ready(self, stats_dict):
        tasks = []
        # Check whether the reading task is healthy
        # while waiting until the device is ready.
        if hasattr(self.device, "wait_reading"):
            tasks.append(gevent.spawn(self.device.wait_reading))
        tasks.append(gevent.spawn(self.device._wait_ready, stats_dict))
        join_tasks(tasks, count=1)
        wait_ready_task = tasks.pop(-1)
        try:
            return wait_ready_task.get()
        finally:
            gevent.killall(tasks, exception=StopTask)

    def _prepare(self, stats_dict):
        self._stats_dict = stats_dict
        self.device._prepare(stats_dict)


class DeviceIterator(AbstractDeviceIterator):
    def __init__(self, device):
        super().__init__()
        self.__device_ref = weakref.ref(device)
        self.__sequence_index = 0

    @property
    def device(self):
        return self.__device_ref()

    def __next__(self):
        if not self.device.parent:
            raise StopIteration
        else:
            if not self.device.prepare_once and not self.device.start_once:
                if hasattr(self.device, "wait_reading"):
                    self.device.wait_reading()
        self.__sequence_index += 1
        return self

    def _prepare(self, stats_dict):
        if self.__sequence_index > 0 and self.device.prepare_once:
            return
        super()._prepare(stats_dict)

    def _start(self, stats_dict):
        if self.__sequence_index > 0 and self.device.start_once:
            return
        self.device._start(stats_dict)


class DeviceIteratorWrapper(AbstractDeviceIterator):
    def __init__(self, device):
        super().__init__()
        self.__device = weakref.proxy(device)
        self.__iterator = iter(device)
        self.__current = None
        next(self)

    @property
    def device(self):
        return self.__current

    def __next__(self):
        try:
            self.__current = next(self.__iterator)
        except StopIteration:
            if not self.__device.parent:
                raise
            if hasattr(self.__device, "wait_reading"):
                self.__device.wait_reading()
            self.__iterator = iter(self.__device)
            self.__current = next(self.__iterator)
        except Exception as e:
            e.args = (self.__device.name, *e.args)
            raise


class ChainPreset:
    """
    This class interface will be called by the chain object
    at the beginning and at the end of a chain iteration.

    A typical usage of this class is to manage the opening/closing
    by software or to control beamline multiplexer(s)
    """

    def get_iterator(self, chain):
        """Yield ChainIterationPreset instances, if needed"""
        pass

    def prepare(self, chain):
        """
        Called on the preparation phase of the chain iteration.
        """
        pass

    def start(self, chain):
        """
        Called on the starting phase of the chain iteration.
        """
        pass

    def before_stop(self, chain):
        """
        Called at the end of the scan just before calling **stop** on detectors
        """
        pass

    def stop(self, chain):
        """
        Called at the end of the chain iteration.
        """
        pass


class ChainIterationPreset:
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


class CompletedCtrlParamsDict(dict):
    """subclass dict to convay the message to AcqObj 
    that ctrl_params have already be treated
    """

    pass


def update_ctrl_params(controller, scan_specific_ctrl_params):
    from bliss.controllers.counter import CounterController

    if isinstance(controller, CounterController):
        parameters = controller.get_current_parameters()
        if parameters and type(parameters) == dict:
            parameters = parameters.copy()
            if not scan_specific_ctrl_params:
                return CompletedCtrlParamsDict(parameters)
            else:
                parameters.update(scan_specific_ctrl_params)
                return CompletedCtrlParamsDict(parameters)

    return CompletedCtrlParamsDict({})


class AcquisitionObject:
    def __init__(
        self,
        *devices,
        name=None,
        npoints=1,
        trigger_type=TRIGGER_MODE_ENUM.SOFTWARE,
        prepare_once=False,
        start_once=False,
        ctrl_params=None,
    ):

        self.__name = name
        self.__parent = None
        self.__channels = AcquisitionChannelList()
        self.__npoints = npoints
        self.__trigger_type = trigger_type
        self.__prepare_once = prepare_once
        self.__start_once = start_once

        self._counters = collections.defaultdict(list)
        self._init(devices)

        if not isinstance(ctrl_params, CompletedCtrlParamsDict):
            self._ctrl_params = self.init_ctrl_params(self.device, ctrl_params)
        else:
            self._ctrl_params = ctrl_params

    def init_ctrl_params(self, device, ctrl_params):
        """ensure that ctrl-params have been completed"""
        if isinstance(ctrl_params, CompletedCtrlParamsDict):
            return ctrl_params
        else:
            return update_ctrl_params(device, ctrl_params)

    @staticmethod
    def get_param_validation_schema():
        """returns a schema dict for validation"""
        raise NotImplementedError

    @classmethod
    def validate_params(cls, acq_params, ctrl_params=None):

        params = {"acq_params": acq_params}

        if ctrl_params:
            assert isinstance(ctrl_params, CompletedCtrlParamsDict)
            params.update({"ctrl_params": ctrl_params})

        validator = BlissValidator(cls.get_param_validation_schema())

        if validator(params):
            return validator.normalized(params)["acq_params"]
        else:
            raise RuntimeError(str(validator.errors))

    @classmethod
    def get_default_acq_params(cls):
        return cls.validate_acq_params({})

    def _init(self, devices):
        self._device, counters = self.init(devices)

        for cnt in counters:
            self.add_counter(cnt)

    def init(self, devices):
        """Return the device and counters list"""
        if devices:
            from bliss.common.counter import Counter  # beware of circular import
            from bliss.common.motor_group import Group
            from bliss.common.axis import Axis

            if all(isinstance(dev, Counter) for dev in devices):
                return devices[0]._counter_controller, devices
            elif all(isinstance(dev, Axis) for dev in devices):
                return Group(*devices), []
            else:
                if len(devices) == 1:
                    return devices[0], []
        else:
            return None, []
        raise TypeError(
            "Cannot handle devices which are not all Counter or Axis objects, or a single object",
            devices,
        )

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
        return self._device

    @property
    def ctrl_params(self):
        return self._ctrl_params

    @property
    def _device_name(self):
        from bliss.common.motor_group import is_motor_group
        from bliss.common.axis import Axis

        if is_motor_group(self.device) or isinstance(self.device, Axis):
            return "axis"
        return self.device.name

    @property
    def name(self):
        return self.__name if self.__name is not None else self._device_name

    @property
    def channels(self):
        return self.__channels

    @property
    def npoints(self):
        return self.__npoints

    def _do_add_counter(self, counter):
        if isinstance(counter, CounterAlias):
            controller_fullname, _, _ = counter.fullname.rpartition(":")
            chan_name = f"{controller_fullname}:{counter.name}"
        else:
            chan_name = counter.fullname

        try:
            unit = counter.unit
        except AttributeError:
            unit = None

        self.channels.append(
            AcquisitionChannel(chan_name, counter.dtype, counter.shape, unit=unit)
        )
        self._counters[counter].append(self.channels[-1])

    def add_counter(self, counter):
        if counter in self._counters:
            return

        if counter._counter_controller == self.device:
            self._do_add_counter(counter)
        else:
            raise RuntimeError(
                f"Cannot add counter {counter.name}: acquisition controller mismatch {counter._counter_controller} != {self.device}"
            )

    # ---------------------POTENTIALLY OVERLOAD METHODS  ----------------------------------------
    def apply_parameters(self):
        """Load controller parameters into hardware controller at the beginning of each scan"""
        from bliss.controllers.counter import CounterController

        if isinstance(self.device, CounterController):
            self.device.apply_parameters(self._ctrl_params)

    def fill_meta_at_scan_start(self, scan_meta):
        """
        In this method, acquisition device should collect and meta data
        related to this device and prepare it for publishing. it is called 
        during the scan initialization. 
        
        This can be used in two ways:
        1) attaching meta data to the scan_meta object and publishing it in scan_info
           i.e: scan_meta.instrument.set(self,{"timing mode":"fast"})
        2) the return value of this function is used to fill the meta data of the
           node attached to this AcqObj
        """
        return None

    def fill_meta_at_scan_end(self, scan_meta):
        """
        In this method, acquisition device should collect and meta data
        related to this device and prepare it for publishing. it is called 
        at the end of the scan. 
        
        This can be used in two ways:
        1) attaching meta data to the scan_meta object and publishing it in scan_info
           i.e: scan_meta.instrument.set(self,{"timing mode":"fast"})
        2) the return value of this function is used to fill the meta data of the
           node attached to this AcqObj
        """
        return None

    # --------------------------- OVERLOAD METHODS  ---------------------------------------------
    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class AcquisitionMaster(AcquisitionObject):

    HARDWARE, SOFTWARE = TRIGGER_MODE_ENUM.HARDWARE, TRIGGER_MODE_ENUM.SOFTWARE

    def __init__(
        self,
        *devices,
        name=None,
        npoints=1,
        trigger_type=TRIGGER_MODE_ENUM.SOFTWARE,
        prepare_once=False,
        start_once=False,
        ctrl_params=None,
    ):

        super().__init__(
            *devices,
            name=name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self.__slaves = list()
        self.__triggers = list()
        self.__duplicated_channels = {}
        self.__prepared = False
        self.__stats_dict = {}
        self.__terminator = True

    @property
    def slaves(self):
        return self.__slaves

    @property
    def terminator(self):
        """bool: flag to specify if the whole scan should terminate when the acquisition under control of the master is done. 

        Only taken into account if the acquisition master is a top master in the acquisition chain.
        Defaults to True: any top master ends a scan when done.
        """
        return self.__terminator

    @terminator.setter
    def terminator(self, terminator):
        self.__terminator = bool(terminator)

    def _prepare(self, stats_dict):
        self.__stats_dict = stats_dict
        with profile(stats_dict, self.name, "prepare"):
            if not self.__prepared:

                for connect, _ in self.__duplicated_channels.values():
                    connect()
                self.__prepared = True

            return self.prepare()

    def _start(self, stats_dict):
        with profile(stats_dict, self.name, "start"):
            dispatcher.send("start", self)
            return_value = self.start()
            return return_value

    def _stop(self, stats_dict):
        with profile(stats_dict, self.name, "stop"):
            if self.__prepared:
                for _, cleanup in self.__duplicated_channels.values():
                    cleanup()
                self.__prepared = False
            return self.stop()

    def _trigger(self, stats_dict):
        with profile(stats_dict, self.name, "trigger"):
            return self.trigger()

    def _wait_ready(self, stats_dict):
        with profile(stats_dict, self.name, "wait_ready"):
            self.wait_ready()

    def trigger_slaves(self):
        stats_dict = self.__stats_dict
        with profile(stats_dict, self.name, "trigger_slaves"):
            invalid_slaves = list()
            for slave, task in self.__triggers:
                if not slave.trigger_ready() or not task.successful():
                    invalid_slaves.append(slave)
                    if task.ready():
                        task.get()  # raise task exception, if any
                    # otherwise, kill the task with RuntimeError
                    task.kill(
                        RuntimeError(
                            "%s: Previous trigger is not done, aborting" % self.name
                        )
                    )

            self.__triggers = []

            if invalid_slaves:
                raise RuntimeError(
                    "%s: Aborted due to bad triggering on slaves: %s"
                    % (self.name, invalid_slaves)
                )
            else:
                for slave in self.slaves:
                    if slave.trigger_type == TRIGGER_MODE_ENUM.SOFTWARE:
                        self.__triggers.append(
                            (slave, gevent.spawn(slave._trigger, stats_dict))
                        )

    def wait_slaves(self):
        stats_dict = self.__stats_dict
        with profile(stats_dict, self.name, "wait_slaves"):
            slave_tasks = [task for _, task in self.__triggers]
            join_tasks(slave_tasks)

    def add_external_channel(
        self, device, name, rename=None, conversion=None, dtype=None
    ):
        """Add a channel from an external source."""
        try:
            source = next(
                channel for channel in device.channels if channel.short_name == name
            )
        except StopIteration:
            raise ValueError(
                "The device {} does not have a channel called {}".format(device, name)
            )
        new_channel, connect, cleanup = duplicate_channel(
            source, name=rename, conversion=conversion, dtype=dtype
        )
        self.__duplicated_channels[new_channel] = connect, cleanup
        self.channels.append(new_channel)

    def attach_channels(self, master, to_channel_name):
        """Attaching all channels from a topper master means that this master
        data channels will be captured and re-emit when the
        **to_channel_name** will emit its data.
        in a case of this kind of chain i.e a mesh:
        m0 (channel: pos_m0)
        └── m1 (channel: pos_m1)
            └── timer (channel: elapsed_time)
        pos_m0 will be emit when pos_m1 will be emit => same amount of values

        Note: this can only work if topper master emit data one by one and before
        this master
        """
        # check if master is a topper master
        parent = self.parent
        while parent is not None and parent != master:
            parent = parent.parent
        if parent is None:  # master is not a parent
            raise RuntimeError(
                "Could only work with a master device (%s) is not a master of (%s)"
                % (master.name, self.name)
            )

        try:
            to_channel = next(
                channel for channel in self.channels if channel.name == to_channel_name
            )
        except StopIteration:
            raise ValueError(
                "The device {} does not have a channel called {}".format(device, name)
            )

        attach_channels(master.channels, to_channel)

    def wait_slaves_prepare(self):
        """
        This method will wait the end of the **prepare**
        one slaves.
        """
        tasks = [
            _f for _f in [_running_task_on_device.get(dev) for dev in self.slaves] if _f
        ]
        join_tasks(tasks)

    def wait_slaves_ready(self):
        """
        This method will wait that all slaves are **ready** to take an other trigger
        """
        for slave in self.slaves:
            if isinstance(slave, AcquisitionMaster):
                slave.wait_slaves_ready()

        tasks = [gevent.spawn(dev.wait_ready) for dev in self.slaves]
        join_tasks(tasks)

    # --------------------------- OVERLOAD METHODS  ---------------------------------------------

    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def trigger(self):
        raise NotImplementedError

    def trigger_ready(self):
        return True

    def wait_ready(self):
        # wait until ready for next acquisition
        # (not considering slave devices)
        pass

    def set_image_saving(self, directory, prefix, force_no_saving=False):
        pass


class AcquisitionSlave(AcquisitionObject):
    HARDWARE, SOFTWARE = TRIGGER_MODE_ENUM.HARDWARE, TRIGGER_MODE_ENUM.SOFTWARE

    def __init__(
        self,
        *devices,
        name=None,
        npoints=1,
        trigger_type=TRIGGER_MODE_ENUM.SOFTWARE,
        prepare_once=False,
        start_once=False,
        ctrl_params=None,
    ):

        super().__init__(
            *devices,
            name=name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self._reading_task = None

    def _prepare(self, stats_dict):
        with profile(stats_dict, self.name, "prepare"):
            if self._reading_task:
                raise RuntimeError("%s: Last reading task is not finished." % self.name)
            return self.prepare()

    def _start(self, stats_dict):
        with profile(stats_dict, self.name, "start"):
            dispatcher.send("start", self)
            self.start()
            if not self._reading_task:
                self._reading_task = gevent.spawn(self.reading)

    def _stop(self, stats_dict):
        with profile(stats_dict, self.name, "stop"):
            self.stop()

    def _trigger(self, stats_dict):
        with profile(stats_dict, self.name, "trigger"):
            if not self._reading_task:
                dispatcher.send("start", self)
                self._reading_task = gevent.spawn(self.reading)
            self.trigger()

    def _wait_ready(self, stats_dict):
        with profile(stats_dict, self.name, "wait_ready"):
            self.wait_ready()

    def wait_reading(self):
        if self._reading_task is not None:
            return self._reading_task.get()
        return True

    # --------------------------- OVERLOAD METHODS  ---------------------------------------------

    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def trigger(self):
        raise NotImplementedError

    def reading(self):
        pass

    def trigger_ready(self):
        return True

    def wait_ready(self):
        # wait until ready for next acquisition
        pass


class AcquisitionChainIter:
    def __init__(
        self, acquisition_chain, sub_tree, presets_list, parallel_prepare=True
    ):
        self.__sequence_index = -1
        self._parallel_prepare = parallel_prepare
        self.__acquisition_chain_ref = weakref.ref(acquisition_chain)
        self._preset_iterators_list = list()
        self._current_preset_iterators_list = list()
        self._presets_list = presets_list
        self._start_time = time.time()

        # create iterators tree
        self._tree = Tree()
        self._root_node = self._tree.create_node("acquisition chain", "root")
        device2iter = dict()
        for dev in sub_tree.expand_tree():
            if not isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                continue
            dev_node = acquisition_chain._tree.get_node(dev)
            parent = device2iter.get(dev_node.bpointer, "root")
            try:
                it = iter(dev)
            except TypeError:
                dev_iter = DeviceIterator(dev)
            else:
                dev_iter = DeviceIteratorWrapper(dev)
            device2iter[dev] = dev_iter
            self._tree.create_node(tag=dev.name, identifier=dev_iter, parent=parent)

    @property
    def acquisition_chain(self):
        return self.__acquisition_chain_ref()

    @property
    def top_master(self):
        return self._tree.children("root")[0].identifier.device

    def apply_parameters(self):
        for tasks in self._execute("apply_parameters", wait_between_levels=False):
            gevent.joinall(tasks, raise_error=True)

    def prepare(self, scan, scan_info):
        preset_tasks = list()
        if self.__sequence_index == 0:
            preset_tasks = [
                gevent.spawn(preset.prepare, self.acquisition_chain)
                for preset in self._presets_list
            ]

            self._preset_iterators_list = list()

            for preset in self._presets_list:
                iterator = preset.get_iterator(self.acquisition_chain)
                if isinstance(iterator, collections.abc.Iterable):
                    self._preset_iterators_list.append(iterator)

        self._current_preset_iterators_list = list()
        for iterator in list(self._preset_iterators_list):
            try:
                preset = next(iterator)
                assert isinstance(preset, ChainIterationPreset)
            except StopIteration:
                self._preset_iterators_list.remove(iterator)
            except:
                sys.excepthook(*sys.exc_info())
                self._preset_iterators_list.remove(iterator)
            else:
                self._current_preset_iterators_list.append(preset)
                preset_tasks.append(gevent.spawn(preset.prepare))

        join_tasks(preset_tasks)

        stats_dict = self.__acquisition_chain_ref()._stats_dict
        for tasks in self._execute(
            "_prepare",
            stats_dict=stats_dict,
            wait_between_levels=not self._parallel_prepare,
        ):
            join_tasks(tasks)

    def start(self):
        preset_tasks = list()
        if self.__sequence_index == 0:
            preset_tasks = [
                gevent.spawn(preset.start, self.acquisition_chain)
                for preset in self._presets_list
            ]

        preset_tasks.extend(
            [gevent.spawn(i.start) for i in self._current_preset_iterators_list]
        )

        join_tasks(preset_tasks)

        stats_dict = self.__acquisition_chain_ref()._stats_dict
        for tasks in self._execute("_start", stats_dict=stats_dict):
            join_tasks(tasks)

    def wait_all_devices(self):
        for acq_dev_iter in (
            x
            for x in self._tree.expand_tree()
            if x is not "root"
            and isinstance(x.device, (AcquisitionSlave, AcquisitionMaster))
        ):
            if hasattr(acq_dev_iter, "wait_reading"):
                acq_dev_iter.wait_reading()
            if isinstance(acq_dev_iter.device, AcquisitionMaster):
                acq_dev_iter.wait_slaves()
            dispatcher.send("end", acq_dev_iter.device)

    def stop(self):
        all_tasks = []
        stats_dict = self.__acquisition_chain_ref()._stats_dict
        with capture_exceptions(raise_index=0) as capture:
            # call before_stop on preset
            with capture():
                preset_tasks = [
                    gevent.spawn(preset.before_stop, self.acquisition_chain)
                    for preset in self._presets_list
                ]

                gevent.joinall(preset_tasks)  # wait to call all before_stop on preset
                gevent.joinall(preset_tasks, raise_error=True)

            for tasks in self._execute(
                "_stop", stats_dict=stats_dict, master_to_slave=True
            ):
                with KillMask(masked_kill_nb=1):
                    gevent.joinall(tasks)
                all_tasks.extend(tasks)

            with capture():
                gevent.joinall(all_tasks, raise_error=True)

            with capture():
                self.wait_all_devices()

            with capture():
                preset_tasks = [
                    gevent.spawn(preset.stop, self.acquisition_chain)
                    for preset in self._presets_list
                ]
                preset_tasks.extend(
                    [gevent.spawn(i.stop) for i in self._current_preset_iterators_list]
                )

                gevent.joinall(preset_tasks)  # wait to call all stop on preset
                gevent.joinall(preset_tasks, raise_error=True)

    def __next__(self):
        self.__sequence_index += 1
        if self.__sequence_index == 0:
            self._start_time = time.time()
        stats_dict = self.__acquisition_chain_ref()._stats_dict
        wait_ready_tasks = self._execute(
            "_wait_ready", stats_dict=stats_dict, master_to_slave=True
        )
        for tasks in wait_ready_tasks:
            join_tasks(tasks)
        try:
            if self.__sequence_index:
                for dev_iter in self._tree.expand_tree():
                    if dev_iter is "root":
                        continue
                    next(dev_iter)
            preset_tasks = [
                gevent.spawn(i.stop) for i in self._current_preset_iterators_list
            ]
            gevent.joinall(preset_tasks)
            gevent.joinall(preset_tasks, raise_error=True)
        except StopIteration:  # should we stop all devices?
            self.wait_all_devices()
            raise
        return self

    def _execute(
        self,
        func_name,
        stats_dict=None,
        master_to_slave=False,
        wait_between_levels=True,
    ):
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
                yield tasks
                tasks = list()
                prev_level = level
            func = getattr(dev, func_name)
            if stats_dict is not None:
                t = gevent.spawn(func, stats_dict)
            else:
                t = gevent.spawn(func)
            _running_task_on_device[dev.device] = t
            tasks.append(t)
        yield tasks

    def __iter__(self):
        return self


class AcquisitionChain:
    def __init__(self, parallel_prepare=False):
        self._tree = Tree()
        self._root_node = self._tree.create_node("acquisition chain", "root")
        self._presets_master_list = weakref.WeakKeyDictionary()
        self._parallel_prepare = parallel_prepare
        self._stats_dict = dict()

    def reset_stats(self):
        """Reset time statistics
        """
        self._stats_dict.clear()

    @property
    def nodes_list(self):
        nodes_gen = self._tree.expand_tree()
        next(nodes_gen)  # first node is 'root'
        return list(nodes_gen)

    def get_node_from_devices(self, *devices):
        """
        Helper method to get AcquisitionMaster/Slave
        from countroller and/or counter, motor.
        This will return a list of nodes in the same order
        as the devices. Node will be None if not found.
        """
        from bliss.common.motor_group import _Group

        looking_device = {d: None for d in devices}
        nb_device = len(devices)
        for node in self.nodes_list:
            if isinstance(node.device, _Group):
                for axis in node.device.axes.values():
                    if axis in looking_device:
                        looking_device[axis] = node
                        nb_device -= 1
                if not nb_device:
                    break
            if node.device in looking_device:
                looking_device[node.device] = node
                nb_device -= 1
                if not nb_device:
                    break
            else:
                for cnt in node._counters:
                    if cnt in looking_device:
                        looking_device[cnt] = node
                        nb_device -= 1
                if not nb_device:
                    break
        return looking_device.values()

    def add(self, master, slave=None):

        # --- handle ChainNodes --------------------------------------
        if isinstance(master, ChainNode):
            master.create_acquisition_object(force=False)
            master = master.acquisition_obj

        if isinstance(slave, ChainNode):
            slave.create_acquisition_object(force=False)
            self.add(master, slave.acquisition_obj)

            for node in slave.children:
                node.create_acquisition_object(force=False)
                self.add(slave.acquisition_obj, node.acquisition_obj)

            return

        # print(f"===== ADD SLAVE {slave}({slave.name}) in MASTER {master} ({master.name})")
        if not isinstance(master, AcquisitionMaster):
            raise TypeError(f"object {master} is not an AcquisitionMaster")

        slave_node = self._tree.get_node(slave)
        master_node = self._tree.get_node(master)

        # --- if slave already exist in chain and new slave is an AcquisitionSlave
        if slave_node is not None and isinstance(slave, AcquisitionSlave):

            # --- if {new master is not the master of the current_slave} and {current_master of current_slave is not root}
            # --- => try to put the same slave under a different master => raise error !
            if (
                self._tree.get_node(slave_node.bpointer) is not self._root_node
                and master is not slave_node.bpointer
            ):
                raise RuntimeError(
                    "Cannot add acquisition device %s to multiple masters, current master is %s"
                    % (slave, slave_node._bpointer)
                )
            else:  # --- if {new master is the master of the current_slave} => same allocation => ignore ok
                # --- if {new master is not the master of the current_slave}
                # ---   and {current_master of current_slave is root} => try to re-allocate a top-level AcqDevice under a new master
                # ---     => it should never append because an AcqDev is never given as a master.

                # user error, multiple add, ignore for now
                return

        # --- if slave already exist in chain and new slave is not an AcquisitionSlave => existing AcqMaster slave under new or existing master
        # --- if slave not already in chain   and new slave is not an AcquisitionSlave => new      AcqMaster slave under new or existing master
        # --- if slave not already in chain   and new slave is     an AcquisitionSlave => new      AcqDevice slave under new or existing master

        if master_node is None:  # --- if new master not in chain
            for node in self.nodes_list:
                if (
                    node.name == master.name
                ):  # --- forribde new master with a name already in use
                    raise RuntimeError(
                        f"Cannot add acquisition master with name '{node.name}`: duplicated name"
                    )

            # --- create a new master node
            master_node = self._tree.create_node(
                tag=master.name, identifier=master, parent="root"
            )
        if slave is not None:
            if slave_node is None:  # --- create a new slave node
                slave_node = self._tree.create_node(
                    tag=slave.name, identifier=slave, parent=master
                )
            else:  # --- move an existing AcqMaster under a different master
                self._tree.move_node(slave, master)

            slave.parent = master

    def add_preset(self, preset, master=None):
        """
        Add a preset on a top-master.
        If it None mean the first in the chain

        Args:
            preset should be inherited for class Preset
            master if None take the first top-master from the chain
        """
        if not isinstance(preset, ChainPreset):
            raise ValueError("Expected ChainPreset instance")
        top_masters = [x.identifier for x in self._tree.children("root")]
        if master is not None and master not in top_masters:
            raise ValueError(f"master {master} not in {top_masters}")

        # set the preset on the chain itself if master is None
        # this is to manage the case where the chain tree is still empty.
        presets_list = self._presets_master_list.setdefault(master or self, list())
        presets_list.append(preset)

    @property
    def top_masters(self):
        return [x.identifier for x in self._tree.children("root")]

    def get_iter_list(self):
        if len(self._tree) > 1:
            # set all slaves into master
            for master in (
                x for x in self._tree.expand_tree() if isinstance(x, AcquisitionMaster)
            ):
                del master.slaves[:]
                master.slaves.extend(self._tree.get_node(master).fpointer)

            top_masters = self.top_masters
            sub_trees = [self._tree.subtree(x) for x in top_masters]

            first_top_master = top_masters.pop(0)
            first_tree = sub_trees.pop(0)
            # default => first top master is also store in self
            presets_list = self._presets_master_list.get(self, list())
            presets_list += self._presets_master_list.get(first_top_master, list())
            iterators = [
                AcquisitionChainIter(
                    self,
                    first_tree,
                    presets_list,
                    parallel_prepare=self._parallel_prepare,
                )
            ]
            iterators.extend(
                [
                    AcquisitionChainIter(
                        self,
                        sub_tree,
                        self._presets_master_list.get(master, list()),
                        parallel_prepare=self._parallel_prepare,
                    )
                    for master, sub_tree in zip(top_masters, sub_trees)
                ]
            )
            return iterators
        else:
            return []

    def append(self, chain, add_presets=False):
        """Append another chain"""
        for master in (
            x for x in chain._tree.expand_tree() if isinstance(x, AcquisitionMaster)
        ):
            for slave in chain._tree.get_node(master).fpointer:
                self.add(master, slave)
        self._tree.show()
        if add_presets:
            for preset in chain._presets_list:
                self.add_preset(preset)


class ChainNode:
    def __init__(self, controller):
        self._controller = controller

        self._counters = []
        self._child_nodes = []

        self._is_master = False
        self._is_top_level = True
        self._acquisition_obj = None

        self._acq_obj_params = None
        self._ctrl_params = None
        self._parent_acq_params = None

        self._calc_dep_nodes = {}  # to store CalcCounterController dependent nodes

    @property
    def controller(self):
        return self._controller

    @property
    def is_master(self):
        return self._is_master

    @property
    def is_top_level(self):
        return self._is_top_level

    @property
    def children(self):
        return self._child_nodes

    @property
    def counters(self):
        return self._counters

    @property
    def acquisition_obj(self):
        return self._acquisition_obj

    @property
    def acquisition_parameters(self):
        return self._acq_obj_params

    @property
    def controller_parameters(self):
        return self._ctrl_params

    def set_parent_parameters(self, parent_acq_params, force=False):
        if parent_acq_params is not None:
            if (
                self._parent_acq_params is not None
                and self._parent_acq_params != parent_acq_params
            ):
                print(
                    f"=== ChainNode WARNING: try to set PARENT_ACQ_PARAMS again: \n Current {self._parent_acq_params} \n New     {parent_acq_params} "
                )

            if force or self._parent_acq_params is None:
                self._parent_acq_params = parent_acq_params

    def set_parameters(self, acq_params=None, ctrl_params=None, force=False):
        """ Store the scan and/or acquisition parameters into the node. 
            These parameters will be used when the acquisition object is instantiated (see self.create_acquisition_object )
            If the parameters have been set already, new parameters will be ignored (except if Force==True).
        """

        if acq_params is not None:
            if self._acq_obj_params is not None and self._acq_obj_params != acq_params:
                print(
                    f"=== ChainNode WARNING: try to set ACQ_PARAMS again: \n Current {self._acq_obj_params} \n New     {acq_params} "
                )

            if force or self._acq_obj_params is None:
                self._acq_obj_params = acq_params

        if ctrl_params is not None:
            if self._ctrl_params is not None and self._ctrl_params != ctrl_params:
                print(
                    f"=== ChainNode WARNING: try to set CTRL_PARAMS again: \n Current {self._ctrl_params} \n New     {ctrl_params} "
                )

            if force or self._ctrl_params is None:
                self._ctrl_params = ctrl_params

            # --- transform scan specific ctrl_params into full set of ctrl_param
            self._ctrl_params = update_ctrl_params(self.controller, self._ctrl_params)

    def add_child(self, chain_node):
        if chain_node not in self._child_nodes:
            self._child_nodes.append(chain_node)
            self._is_master = True
            chain_node._is_top_level = False

    def add_counter(self, counter):
        self._counters.append(counter)

    def _get_default_chain_parameters(self, scan_params, acq_params):
        """ Obtain the full acquisition parameters set from scan_params in the context of the default chain """

        return self.controller.get_default_chain_parameters(scan_params, acq_params)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        """ Return the acquisition object associated to this node 
            acq_params, ctrl_params and parent_acq_params have to be dicts (None not supported)
        """

        return self.controller.get_acquisition_object(
            acq_params, ctrl_params=ctrl_params, parent_acq_params=parent_acq_params
        )

    def create_acquisition_object(self, force=False):
        """ Create the acquisition object using the current parameters (stored in 'self._acq_obj_params').
            Create the children acquisition objects if any are attached to this node.
            
            - 'force' (bool): if False, it won't instanciate the acquisition object if it already exists, else it will overwrite it.

        """

        # --- Return acquisition object if it already exist and Force is False ----------------------------
        if not force and self._acquisition_obj is not None:
            return self._acquisition_obj

        # --- Prepare parameters -----------------------------------------------------------------------------------------
        if self._acq_obj_params is None:
            acq_params = {}
        else:
            acq_params = (
                self._acq_obj_params.copy()
            )  # <= IMPORTANT: pass a copy because the acq obj may pop on that dict!

        if self._ctrl_params is None:
            ctrl_params = update_ctrl_params(self.controller, {})
        else:
            ctrl_params = self._ctrl_params

        if self._parent_acq_params is None:
            parent_acq_params = {}
        else:
            parent_acq_params = (
                self._parent_acq_params.copy()
            )  # <= IMPORTANT: pass a copy because the acq obj may pop on that dict!

        # --- Create the acquisition object -------------------------------------------------------
        acq_obj = self.get_acquisition_object(
            acq_params, ctrl_params=ctrl_params, parent_acq_params=parent_acq_params
        )

        if not isinstance(acq_obj, AcquisitionObject):
            raise TypeError(f"Object: {acq_obj} is not an AcquisitionObject")
        else:
            self._acquisition_obj = acq_obj

        # --- Add the counters to the acquisition object ---------------
        for counter in self._counters:
            self._acquisition_obj.add_counter(counter)

        # --- Deal with children acquisition objects ------------------
        self.create_children_acq_obj(force)

        return self._acquisition_obj

    def create_children_acq_obj(self, force=False):
        for node in self.children:

            if node._acq_obj_params is None:
                node.set_parent_parameters(self._acq_obj_params)

            node.create_acquisition_object(force)

    def get_repr_str(self):
        if self._acquisition_obj is None:
            txt = f"|__ !* {self._controller.name} *! "
        else:
            txt = f"|__ {self._acquisition_obj.__class__.__name__}( {self._controller.name} ) "

        if len(self._counters) > 0:
            txt += "("
            for cnt in self._counters:
                txt += f" {cnt.name},"
            txt = txt[:-1]
            txt += " ) "

        txt += "|"

        return txt
