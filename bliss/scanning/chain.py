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

import gevent
from treelib import Tree

from bliss.common.protocols import HasMetadataForScan
from bliss.common.event import dispatcher
from bliss.common.alias import CounterAlias
from bliss.common.cleanup import capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.scanning.channel import AcquisitionChannelList, AcquisitionChannel
from bliss.scanning.channel import duplicate_channel, attach_channels
from bliss.common.validator import BlissValidator
from bliss.scanning.scan_meta import META_TIMING


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


def join_tasks(greenlets, **kw):
    try:
        gevent.joinall(greenlets, raise_error=True, **kw)
    except StopTask as e:
        gevent.killall(greenlets, exception=type(e))
        raise
    except BaseException:
        gevent.killall(greenlets)
        raise


class AbstractAcquisitionObjectIterator:
    """
    Iterate over an AcquisitionObject, yielding self.
    """

    @property
    def acquisition_object(self):
        raise NotImplementedError

    def __next__(self):
        """Returns self
        """
        raise NotImplementedError

    def __getattr__(self, name):
        """Get attribute from the acquisition object
        """
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.acquisition_object, name)


class AcquisitionObjectIteratorObsolete(AbstractAcquisitionObjectIterator):
    """Use for acquisition objects that are not iterable.
    """

    def __init__(self, acquisition_object):
        super().__init__()
        self.__acquisition_object_ref = weakref.ref(acquisition_object)
        self.__sequence_index = 0

    @property
    def acquisition_object(self):
        return self.__acquisition_object_ref()

    def __next__(self):
        if not self.acquisition_object.parent:
            raise StopIteration
        once = (
            self.acquisition_object.prepare_once or self.acquisition_object.start_once
        )
        if not once:
            self.acquisition_object.acq_wait_reading()
        self.__sequence_index += 1
        return self

    def acq_prepare(self):
        if self.__sequence_index > 0 and self.acquisition_object.prepare_once:
            return
        self.acquisition_object.acq_prepare()

    def acq_start(self):
        if self.__sequence_index > 0 and self.acquisition_object.start_once:
            return
        self.acquisition_object.acq_start()


class AcquisitionObjectIterator(AbstractAcquisitionObjectIterator):
    """Use for acquisition objects that are iterable.
    """

    def __init__(self, acquisition_object):
        super().__init__()
        self.__acquisition_object = weakref.proxy(acquisition_object)
        self.__iterator = iter(acquisition_object)
        self.__current_acq_object = None
        next(self)

    @property
    def acquisition_object(self):
        return self.__current_acq_object

    def __next__(self):
        try:
            self.__current_acq_object = next(self.__iterator)
        except StopIteration:
            if not self.__acquisition_object.parent:
                raise
            self.__acquisition_object.acq_wait_reading()
            # Restart iterating:
            self.__iterator = iter(self.__acquisition_object)
            self.__current_acq_object = next(self.__iterator)
        except Exception as e:
            e.args = (self.__acquisition_object.name, *e.args)
            raise
        return self


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

        if self.device is None:
            return None
        if is_motor_group(self.device) or isinstance(self.device, Axis):
            return "axis"
        return self.device.name

    @property
    def name(self):
        if self.__name:
            return self.__name
        else:
            return self._device_name

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
                f"Cannot add counter {counter.name}: acquisition controller"
                f" mismatch {counter._counter_controller} != {self.device}"
            )

    def get_iterator(self):
        try:
            iter(self)
        except (NotImplementedError, TypeError):
            return AcquisitionObjectIteratorObsolete(self)
        else:
            return AcquisitionObjectIterator(self)

    # --------------------------- ACQ. CHAIN METHODS ------------------------------------------

    def has_reading_task(self):
        """Returns True when the underlying device has a reading task.
        """
        # TODO: very convoluted. AcquisitionSlave always has a reading task
        # while AcquisitionMaster sometimes has a reading task.
        return hasattr(self, "wait_reading")

    def acq_wait_reading(self):
        """Wait until reading task has finished
        """
        if self.has_reading_task():
            self.wait_reading()

    def acq_wait_ready(self):
        """Wait until ready for next acquisition
            """
        tasks = []
        # The acquistion object is also considered to be
        # ready when the reading task (if any) is not running.
        if self.has_reading_task():
            tasks.append(gevent.spawn(self.wait_reading))
        tasks.append(gevent.spawn(self.wait_ready))
        join_tasks(tasks, count=1)
        wait_ready_task = tasks.pop(-1)
        try:
            return wait_ready_task.get()
        finally:
            gevent.killall(tasks, exception=StopTask)

    # --------------------------- OVERLOAD ACQ. CHAIN METHODS ---------------------------------

    def acq_prepare(self):
        raise NotImplementedError

    def acq_start(self):
        raise NotImplementedError

    def acq_stop(self):
        raise NotImplementedError

    def acq_trigger(self):
        raise NotImplementedError

    # ---------------------POTENTIALLY OVERLOAD METHODS  ----------------------------------------

    def apply_parameters(self):
        """Load controller parameters into hardware controller at the beginning of each scan"""
        from bliss.controllers.counter import CounterController

        if isinstance(self.device, CounterController):
            self.device.apply_parameters(self._ctrl_params)

    META_TIMING = META_TIMING

    def get_acquisition_metadata(self, timing=None):
        """
        In this method, acquisition device should collect time-dependent
        any meta data related to this device.
        """
        if timing == META_TIMING.PREPARED:
            device = self.device
            if isinstance(device, HasMetadataForScan):
                return device.scan_metadata()
        return None

    # --------------------------- OVERLOAD METHODS  ---------------------------------------------

    def prepare(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def wait_ready(self):
        # wait until ready for next acquisition
        pass

    def __iter__(self):
        """Needs to yield AcquisitionObject instances when implemented
        """
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

    def acq_prepare(self):
        if not self.__prepared:

            for connect, _ in self.__duplicated_channels.values():
                connect()
            self.__prepared = True

        return self.prepare()

    def acq_start(self):
        dispatcher.send("start", self)
        return_value = self.start()
        return return_value

    def acq_stop(self):
        if self.__prepared:
            for _, cleanup in self.__duplicated_channels.values():
                cleanup()
            self.__prepared = False
        return self.stop()

    def acq_trigger(self):
        return self.trigger()

    def trigger_slaves(self):
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
                    self.__triggers.append((slave, gevent.spawn(slave.acq_trigger)))

    def wait_slaves(self):
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
        ????????? m1 (channel: pos_m1)
            ????????? timer (channel: elapsed_time)
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
                f"The device {master} does not have a channel called {to_channel_name}"
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

    def stop_all_slaves(self):
        """
        This method will stop all slaves depending of this master
        """
        for slave in self.slaves:
            if isinstance(slave, AcquisitionMaster):
                slave.stop_all_slaves()

        tasks = [gevent.spawn(dev.stop) for dev in self.slaves]
        try:
            gevent.joinall(tasks, raise_error=True)
        finally:
            gevent.killall(tasks)

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

    def acq_prepare(self):
        if self._reading_task:
            raise RuntimeError("%s: Last reading task is not finished." % self.name)
        return self.prepare()

    def acq_start(self):
        dispatcher.send("start", self)
        self.start()
        if not self._reading_task:
            self._reading_task = gevent.spawn(self.reading)

    def acq_stop(self):
        self.stop()

    def acq_trigger(self):
        if not self._reading_task:
            dispatcher.send("start", self)
            self._reading_task = gevent.spawn(self.reading)
        self.trigger()

    def wait_reading(self):
        if self._reading_task is not None:
            self._reading_task.get()

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
        acqobj2iter = dict()
        for acq_obj in sub_tree.expand_tree():
            if not isinstance(acq_obj, AcquisitionObject):
                continue
            node = acquisition_chain._tree.get_node(acq_obj)
            parent_acq_obj_iter = acqobj2iter.get(node.bpointer, "root")
            acqobj2iter[acq_obj] = acq_obj_iter = acq_obj.get_iterator()
            self._tree.create_node(
                tag=acq_obj.name, identifier=acq_obj_iter, parent=parent_acq_obj_iter
            )

    @property
    def acquisition_chain(self):
        return self.__acquisition_chain_ref()

    @property
    def top_master(self):
        return self._tree.children("root")[0].identifier.acquisition_object

    def apply_parameters(self):
        for tasks, _ in self._execute("apply_parameters", wait_between_levels=False):
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

        for tasks, _ in self._execute(
            "acq_prepare", wait_between_levels=not self._parallel_prepare
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

        for tasks, _ in self._execute("acq_start"):
            join_tasks(tasks)

    def _acquisition_object_iterators(self):
        for acq_obj_iter in self._tree.expand_tree():
            if not isinstance(acq_obj_iter, AbstractAcquisitionObjectIterator):
                continue
            yield acq_obj_iter

    def wait_all_devices(self):
        for acq_obj_iter in self._acquisition_object_iterators():
            acq_obj_iter.acq_wait_reading()
            if isinstance(acq_obj_iter.acquisition_object, AcquisitionMaster):
                acq_obj_iter.wait_slaves()
            dispatcher.send("end", acq_obj_iter.acquisition_object)

    def stop(self):
        all_tasks = []
        all_acq_objs = []
        with capture_exceptions(raise_index=0) as capture:
            # call before_stop on preset
            with capture():
                preset_tasks = [
                    gevent.spawn(preset.before_stop, self.acquisition_chain)
                    for preset in self._presets_list
                ]

                gevent.joinall(preset_tasks)  # wait to call all before_stop on preset
                gevent.joinall(preset_tasks, raise_error=True)

            for tasks, acq_objs in self._execute("acq_stop", master_to_slave=True):
                with KillMask(masked_kill_nb=1):
                    gevent.joinall(tasks)
                all_tasks.extend(tasks)
                all_acq_objs.extend(acq_objs)
            for i, task in enumerate(all_tasks):
                with capture():
                    try:
                        task.get()
                    except BaseException:
                        acq_obj = all_acq_objs[i]
                        if hasattr(acq_obj, "_reading_task"):
                            acq_obj._reading_task.kill()
                        raise
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
        wait_ready_tasks = self._execute("acq_wait_ready", master_to_slave=True)
        for tasks, _ in wait_ready_tasks:
            join_tasks(tasks)
        try:
            if self.__sequence_index:
                for acq_obj_iter in self._acquisition_object_iterators():
                    next(acq_obj_iter)
            preset_tasks = [
                gevent.spawn(i.stop) for i in self._current_preset_iterators_list
            ]
            gevent.joinall(preset_tasks)
            gevent.joinall(preset_tasks, raise_error=True)
        except StopIteration:  # should we stop all devices?
            self.wait_all_devices()
            raise
        return self

    def _execute(self, func_name, master_to_slave=False, wait_between_levels=True):
        tasks = []
        acq_objs = []
        prev_level = None
        if master_to_slave:
            acq_obj_iters = list(self._tree.expand_tree(mode=Tree.WIDTH))[1:]
        else:
            acq_obj_iters = reversed(list(self._tree.expand_tree(mode=Tree.WIDTH))[1:])

        for acq_obj_iter in acq_obj_iters:
            node = self._tree.get_node(acq_obj_iter)
            level = self._tree.depth(node)
            if wait_between_levels and prev_level != level:
                yield tasks, acq_objs
                acq_objs = []
                tasks = []
                prev_level = level
            func = getattr(acq_obj_iter, func_name)
            t = gevent.spawn(func)
            _running_task_on_device[acq_obj_iter.acquisition_object] = t
            acq_objs.append(acq_obj_iter.acquisition_object)
            tasks.append(t)
        yield tasks, acq_objs

    def __iter__(self):
        return self


class AcquisitionChain:
    def __init__(self, parallel_prepare=False):
        self._tree = Tree()
        self._root_node = self._tree.create_node("acquisition chain", "root")
        self._presets_master_list = weakref.WeakKeyDictionary()
        self._parallel_prepare = parallel_prepare

    @property
    def tree(self) -> Tree:
        """Return the acquisition chain tree"""
        return self._tree

    @property
    def top_masters(self):
        return [x.identifier for x in self._tree.children("root")]

    @property
    def nodes_list(self):
        nodes_gen = self._tree.expand_tree()
        next(nodes_gen)  # first node is 'root'
        return list(nodes_gen)

    def get_node_from_devices(self, *devices):
        """
        Helper method to get AcquisitionObject
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

        Args:
            preset: a ChainPreset object
            master: if None, take the first top-master of the chain
        """
        if not isinstance(preset, ChainPreset):
            raise ValueError("Expected ChainPreset instance")
        top_masters = self.top_masters
        if master is not None and master not in top_masters:
            raise ValueError(f"master {master} not in {top_masters}")

        # set the preset on the chain itself if master is None
        # this is to manage the case where the chain tree is still empty.
        presets_list = self._presets_master_list.setdefault(master or self, list())
        presets_list.append(preset)

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
                    f"=== ChainNode WARNING: try to set PARENT_ACQ_PARAMS again: \n"
                    f"Current {self._parent_acq_params} \n New     {parent_acq_params} "
                )

            if force or self._parent_acq_params is None:
                self._parent_acq_params = parent_acq_params

    def set_parameters(self, acq_params=None, ctrl_params=None, force=False):
        """
        Store the scan and/or acquisition parameters into the node.
        These parameters will be used when the acquisition object
        is instantiated (see self.create_acquisition_object )
        If the parameters have been set already, new parameters will
        be ignored (except if Force==True).
        """

        if acq_params is not None:
            if self._acq_obj_params is not None and self._acq_obj_params != acq_params:
                print(
                    f"=== ChainNode WARNING: try to set ACQ_PARAMS again: \n"
                    f"Current {self._acq_obj_params} \n New     {acq_params} "
                )

            if force or self._acq_obj_params is None:
                self._acq_obj_params = acq_params

        if ctrl_params is not None:
            if self._ctrl_params is not None and self._ctrl_params != ctrl_params:
                print(
                    f"=== ChainNode WARNING: try to set CTRL_PARAMS again: \n"
                    f"Current {self._ctrl_params} \n New     {ctrl_params} "
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
        """
        Obtain the full acquisition parameters set from scan_params
        in the context of the default chain
        """

        return self.controller.get_default_chain_parameters(scan_params, acq_params)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        """
        Return the acquisition object associated to this node
        acq_params, ctrl_params and parent_acq_params have to be
        dicts (None not supported)
        """

        return self.controller.get_acquisition_object(
            acq_params, ctrl_params=ctrl_params, parent_acq_params=parent_acq_params
        )

    def create_acquisition_object(self, force=False):
        """
        Create the acquisition object using the current
        parameters (stored in 'self._acq_obj_params').
        Create the children acquisition objects if any are attached to this node.
        - 'force' (bool): if False, it won't instanciate the acquisition
           object if it already exists, else it will overwrite it.
        """

        # --- Return acquisition object if it already exist and Force is False ----------------
        if not force and self._acquisition_obj is not None:
            return self._acquisition_obj

        # --- Prepare parameters --------------------------------------------------------------
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

        # --- Create the acquisition object ---------------------------------------------------
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
