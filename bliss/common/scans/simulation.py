# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import numpy
import gevent

from bliss.scanning.chain import AcquisitionMaster
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.toolbox import ChainBuilder

from bliss.scanning.chain import AcquisitionSlave, TRIGGER_MODE_ENUM
from bliss.scanning.acquisition.motor import MotorMaster, LinearStepTriggerMaster

from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.scan_info import ScanInfo

from bliss.common.counter import Counter
from bliss.common import event as levent
from bliss.controllers.counter import CalcCounterController, CounterController
from bliss.controllers.counter import SamplingCounterController

from bliss.common.utils import all_equal, deep_update

from bliss.common.scans.meshes import amesh

from bliss.common.image_tools import (
    file_to_pil,
    array_to_pil,
    pil_to_array,
    get_image_display,
    test_image,
)

from bliss.common.protocols import HasMetadataForScan


# CHAIN OBJECT NOTES:
#
# AcquisitionChainIter:
#   <== AcquisitionChainIter._execute("apply_parameters", wait_between_levels=False)                       <==
#   <== AcquisitionChainIter._execute("acq_prepare",      wait_between_levels=not self._parallel_prepare)  <==
#   <== AcquisitionChainIter._execute("acq_start")                                                         <==
#   ==> AcquisitionChainIter._execute("acq_wait_ready", master_to_slave=True)  ==>
#   ==> AcquisitionChainIter._execute("acq_stop",       master_to_slave=True)  ==>
#
#
# AcquisitionMaster.acq_start:        # (called by AcquisitionChainIter)
#   self.start()  # (default) => raise NotImplementedError
#
# AcquisitionMaster.acq_trigger:      # (optional)
#   self.trigger() # (default) => raise NotImplementedError
#
# AcquisitionMaster.trigger_slaves:   # (optional) Never called by default (can be called in AcquisitionMaster.trigger)
#   ...
#   for slave in self.slaves:
#       if slave.trigger_type == TRIGGER_MODE_ENUM.SOFTWARE:
#            self.__triggers.append((slave, gevent.spawn(slave.acq_trigger)))
#
#
#
# AcquisitionSlave.acq_trigger:   # (optional) can be called via AcquisitionMaster.trigger_slaves
#   if not self._reading_task:
#       self._reading_task = gevent.spawn(self.reading)   # (default) self.reading => pass    (SPAWN READING)
#   self.trigger() # (default) => raise NotImplementedError

# AcquisitionSlave.acq_start:  # (called by AcquisitionChainIter)
#   self.start() => raise NotImplementedError
#   if not self._reading_task:
#       self._reading_task = gevent.spawn(self.reading)     (SPAWN READING)


# BY DEFAULT:
# - only 'AcquisitionObject.start' must be overloaded (master and slave)
# - AcquisitionSlave.acq_start() => SPAWN AcquisitionSlave.reading()
# - _ScanIterationsRunner._run_next => iter.prepare() => _execute("acq_prepare")   (always called)
#                                   => iter.start()   => _execute("acq_start")     (always called)
# - 'AcqObj.acq_start' is called once or at each scan iter (see AcqObj.start_once)
# - 'AcqObj.acq_prepare' is called once or at each scan iter (see AcqObj.prepare_once)
# - Whatever start_once/prepare_once, AcquisitionSlave.reading() is always spawned at each scan iter (if not already alive)


# ** Step_by_step scan (SOFTWARE TRIGGERING) **
# => VariableStepMaster or TimeMaster produces: [start, step, ..., step, stop] chain iterations
# i.e. the AcqMaster will trigger its children (AcqSlaves) at each step.
# In that case the devices (FakeControllers) perform one measurement at each step (read_all).
# device.read_all is called by the device AcqObj (FakeAcquisitionSlave in software mode)
#
#
# ** Continuous scan (HARDWARE TRIGGERING) **
# => MotorMaster => Only produces [start, stop] chain iterations.
# i.e. the measurements acquired during MotorMaster motion are triggered by an HARDWARE signal.
# It requires a MasterCard (FakeAcquisitionCard/FakeAcquisitionCardMaster) that generates the hardware triggers.
#
# The devices (FakeControllers) that receive the signals are put in accumulation state @start
# (started on the 'Start' of the chain iterations from the AcqMaster).
# In a reading loop, the controller waits an hardware trigger to perform one measurement and buffer it.
# It exits the reading loop if npoints are acquired (or abort).
#
# Polling AcqSlave: The device data buffer is read/emptied (data packets) by the AcqObj.reading method (via device.get_values)
# (FakeAcquisitionSlave) which then emits data via channels
#


class Clock:
    def __init__(self):
        self.offset = None
        self.reset()

    def reset(self):
        self.offset = time.time()

    def time(self):
        return time.time() - self.offset


_CLOCK = Clock()


class FakeCounter(Counter):
    """ Fake Counter 1D associated with FakeController """

    def __init__(
        self,
        name,
        controller,
        conversion_function=None,
        unit=None,
        data_gen=None,
        data_size=None,
        data_type=None,
    ):

        if data_gen is None:
            data_gen = "random"

        if data_size is None:
            data_size = ()
        elif not isinstance(data_size, (tuple, list)):
            data_size = (int(data_size),)

        if data_type is None:
            data_type = numpy.float

        self._data_gen = data_gen
        self._data_size = data_size
        self._data_type = data_type

        super().__init__(name, controller, conversion_function, unit)

    @property
    def data_gen(self):
        return self._data_gen

    @property
    def data_size(self):
        return self._data_size

    @property
    def data_type(self):
        return self._data_type

    @property
    def dtype(self):
        return self._data_type

    @property
    def shape(self):
        return self._data_size


class FakeController(CounterController):
    """ 
        Fake controller which can simulates hardware triggering.
        If placed under a FakeAcquisitionCard it will react to signals
        sent by the fake card. On this event the method 'on_trigger_event()'
        is called.

        Default config:
        cfg = {'counters':
                [ {'counter_name':'fake0D', 'data_gen':'random', } ,  # random scalars
                  {'counter_name':'fake1D', 'data_gen': 1, 'data_size':1024, } ,  # spectrums of 1024 values, all equal to 1:
                  {'counter_name':'fake0D', 'data_gen': 'img_square', } , # pixels of an image of a square
                ], }
    """

    def __init__(self, name, config=None):
        super().__init__(name)

        if config is None:
            config = {
                "counters": [
                    {"counter_name": "fake0D", "data_size": (), "data_gen": "random"},
                    {"counter_name": "fake1D", "data_size": 1024, "data_gen": 1},
                    {"counter_name": "fakePix", "data_gen": "img_square"},
                ]
            }

        self._config = config
        self._trigger_type = TRIGGER_MODE_ENUM.SOFTWARE
        self._recv_triggers = 0

        self.load_config()

    def load_config(self):
        """ create counters with fake data from configuration """

        # cfg = {'counters':[ {'counter_name':'fake1D','data_size':(1024,), 'data_gen':'random',},],}

        for cfg in self._config.get("counters", []):
            self.create_counter(
                FakeCounter,
                name=cfg["counter_name"],
                data_gen=cfg.get("data_gen"),
                data_size=cfg.get("data_size"),
                data_type=cfg.get("data_type"),
            )

    @property
    def trigger_type(self):
        return self._trigger_type

    @trigger_type.setter
    def trigger_type(self, value):
        if value not in TRIGGER_MODE_ENUM:
            raise ValueError(
                f"invalid trigger type, should be in {list(TRIGGER_MODE_ENUM)}"
            )
        self._trigger_type = value

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return FakeAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):

        # Return required parameters
        params = {}
        params["npoints"] = acq_params.get("npoints", scan_params.get("npoints", 1))
        params["count_time"] = acq_params.get(
            "count_time", scan_params.get("count_time", 1)
        )
        params["trigger_type"] = acq_params.get("trigger_type", self._trigger_type)
        params["prepare_once"] = acq_params.get("prepare_once", True)
        params["start_once"] = acq_params.get("start_once", True)
        params["read_all_triggers"] = acq_params.get("read_all_triggers", False)

        return params

    def _prepare_counters_data(self, npoints):
        print(f"=== FakeController._prepare_counters_data")
        self._cnts_values = {}
        self._last_indexes = {}
        for cnt in self.counters:
            if isinstance(cnt, FakeCounter):
                cnt_values = self._generate_cnt_data(cnt, npoints)
                self._cnts_values[cnt] = cnt_values
                self._last_indexes[cnt] = 0

    def _generate_cnt_data(self, cnt, npoints):

        # TO DO: take in charge the cnt.data_type

        if cnt.data_gen == "img_square":
            w = h = int(npoints ** 0.5)
            cnt_values = numpy.zeros((h, w))
            cnt_values[1, :] = 1
            cnt_values[h - 2, :] = 1
            cnt_values[:, 1] = 1
            cnt_values[:, w - 2] = 1
            return cnt_values.ravel()

        dim = len(cnt.data_size)
        if dim > 2:
            raise ValueError(f"cannot deal with a dimension of {dim}")

        if dim == 0:
            if cnt.data_gen == "random":
                cnt_values = numpy.random.randint(0, 100, npoints)
            else:
                cnt_values = [
                    cnt.data_gen
                ] * npoints  # an iterator would be much better

        elif dim == 1:
            if cnt.data_gen == "random":
                cnt_values = [
                    numpy.random.randint(0, 100, cnt.data_size[0])
                    for i in range(npoints)
                ]
            else:
                cnt_value = [cnt.data_gen] * cnt.data_size[0]
                cnt_values = [cnt_value] * npoints  # an iterator would be much better

        elif dim == 2:
            w, h = cnt.data_size
            if cnt.data_gen == "random":
                cnt_values = [
                    numpy.random.randint(0, 100, w * h).reshape(h, w)
                    for i in range(npoints)
                ]
            else:
                cnt_value = numpy.ones((h, w)) * cnt.data_gen
                cnt_values = [cnt_value] * npoints  # an iterator would be much better

        else:
            raise ValueError(f"cannot deal with a dimension of {dim}")

        return cnt_values

    def _incr_data_index(self, cnt):
        self._last_indexes[cnt] += 1
        if self._last_indexes[cnt] >= len(self._cnts_values[cnt]):
            self._last_indexes[cnt] = 0

    def get_values(self, from_index, *counters):
        """ Used when simulating Hardware trigger mode """
        return [
            self._cnts_values[cnt][from_index : self._recv_triggers] for cnt in counters
        ]

    def read_all(self, *counters):
        """ Used when simulating Software trigger mode.
            It returns the counters values read from the pre-built data '_cnts_values'.
            Each read_all() increments '_last_indexes[cnt]' ( looping if index >= len(data) ). 
        """
        cnts_value = []
        for cnt in counters:
            idx = self._last_indexes[cnt]
            value = self._cnts_values[cnt][idx]
            cnts_value.append(value)
            self._incr_data_index(cnt)
        return cnts_value

    def on_trigger_event(self):
        print(f"FakeController.on_trigger_event@{_CLOCK.time()}")
        self._recv_triggers += 1


class FakeAcquisitionSlave(AcquisitionSlave):
    """ AcquisitionObject for FakeControllers.

        As an AcquisitionSlave it won't trigger anyone below in the AcqChain
        and self.reading is spwaned at each scan iteration (if not alive already).

        ** In Hardware trigger mode **:
           Designed for devices that accumulate the measurements into a buffer when
           they are periodically triggered by a (fake) hardware signal (usually between 2 scan iterations/steps).

           (reading): self.device is polled until 'npoints' are read for all counters.
           Data packets are read with self.device.get_values(from_index, *cnts).

         ** In software trigger mode **:
            Designed for devices that perform  measurements at each scan iteration only
            (i.e. nothing between 2 scan iterations/steps)

    """

    def __init__(
        self,
        device,
        npoints=1,
        count_time=1,
        trigger_type=None,
        prepare_once=True,
        start_once=False,
        ctrl_params=None,
        read_all_triggers=False,
    ):

        # Use controller trigger_type by default
        if trigger_type is None:
            trigger_type = device.trigger_type

        name = f"{device.name}_FS"
        super().__init__(
            device,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
            name=name,
        )

        self.count_time = count_time
        self.read_all_triggers = read_all_triggers
        # self._event = gevent.event.Event()

    def _emit_new_data(self, data):
        self.channels.update_from_iterable(data)

        # self.channels.update_from_iterable(self, iterable)
        # self.channels.update_from_array(data)
        # self.channels.update({self.chname: self.positions})

    def get_acquisition_metadata(self, timing=None):
        tmp_dict = super().get_acquisition_metadata(timing=timing)
        if timing != self.META_TIMING.PREPARED:
            return tmp_dict
        for cnt in self._counters:
            if isinstance(cnt, HasMetadataForScan):
                mdata = cnt.scan_metadata()
                if mdata is not None:
                    if tmp_dict is None:
                        tmp_dict = dict()
                    deep_update(tmp_dict, mdata)
        return tmp_dict

    def prepare(self):
        print("=== FakeAcquisitionSlave preparing")
        self.device._prepare_counters_data(self.npoints)
        print("=== FakeAcquisitionSlave prepared")

    def start(self):
        print("=== FakeAcquisitionSlave starting")
        self._nb_acq_points = 0
        self._stop_flag = False
        self.device._recv_triggers = 0
        print("=== FakeAcquisitionSlave started")

    def stop(self):
        print("=== FakeAcquisitionSlave stopping")
        self._stop_flag = True
        # self._event.set()
        print("=== FakeAcquisitionSlave stopped")

    def trigger(self):
        print("=== FakeAcquisitionSlave has been triggered")
        # self._event.set()

    def reading(self):
        """ Reading is always spawn (AcqSlave) by the Scan at each iteration """

        # WARNING: in HARDWARE trigger mode:
        # reading is spawn (by AcqSlave.start) before the AcqMaster.start.
        # so the while loop should wait for the AcqMaster to start before polling on data.
        # If the data buffer of the slave controller is empty it will works because data polling will not
        # find data, so it wont increment _nb_acq_points.
        # If the data buffer is not empty (full of last acq data) then the polling while find all data and retrieve them!
        # to avoid that, at the begining of the loop, it should wait that its triggering master has started.

        print(
            f"=== FakeAcquisitionSlave starts reading in mode {self.trigger_type.name}"
        )
        # self._counters is a dict {Counter: AcquisitionChannel}
        counters = list(self._counters.keys())

        if self.trigger_type == TRIGGER_MODE_ENUM.SOFTWARE:

            cnts_values = [
                counters[i].conversion_function(cnt_values_from_index)
                for i, cnt_values_from_index in enumerate(
                    self.device.read_all(*counters)
                )
            ]

            self._emit_new_data(cnts_values)

        elif self.trigger_type == TRIGGER_MODE_ENUM.HARDWARE:

            while self.device._recv_triggers == 0 and not self._stop_flag:
                gevent.sleep(0.005)

            # wait for the call to self.trigger()
            # self._event.clear()
            # self._event.wait()

            while (
                not self.npoints or self._nb_acq_points < self.npoints
            ) and not self._stop_flag:

                # FOR EACH COUNTER GET THE LAST MEASUREMENTS FROM LAST INDEX (self._nb_acq_points)
                # ONE MEASUREMENT COULD BE A SPECTRUM
                cnts_values = [
                    counters[i].conversion_function(cnt_values_from_index)
                    for i, cnt_values_from_index in enumerate(
                        self.device.get_values(self._nb_acq_points, *counters)
                    )
                ]

                # CHECK THAT ALL COUNTERS HAS RETURNED THE SAME AMOUT OF MEASUREMENTS
                if not all_equal([len(cnt_values) for cnt_values in cnts_values]):
                    raise RuntimeError("Read data can't have different sizes")

                # CHECK THAT THE NUMBER OF MEASUREMENTS OF THE FIRST COUNTER IS > 0
                nb_values = len(cnts_values[0])
                if nb_values > 0:
                    for i, cnt in enumerate(counters):

                        print(
                            f"{cnt.name} (recv_trig_nb={self.device._recv_triggers}) emmitting {nb_values} values of shape {cnt.shape}"
                        )
                    self._nb_acq_points += nb_values
                    self._emit_new_data(cnts_values)

                # gevent.sleep(self.count_time / 2.0)
                gevent.sleep(0.02)

        print(f"=== FakeAcquisitionSlave exits reading")


class FakeAcquisitionCard(FakeController):

    """ 
        Simulates an acquisition card that sends signals to
        registered devices and can read data on its channels.

        A device is registered by giving a callback that will by called
        when the hardware trigger is emitted.

        A FakeAcquisitionCardMaster on top of this object will automatically register
        any slave device under him if it has a 'device.on_trigger_event' method.

        ** Like a Musst card **:
        
        - a custom program can be defined by overloading the method
        'program(nb_triggers, delta_time)' 

        - channels can be configured and can be read during the program.
          To simulate the reading of the card channels, a callback is 
          associated to the channel number.

          ex: cfg = {'channels':[ {'channel':1,'read_func':read_fast_motor,},
                                  {'channel':2,'read_func':read_slow_motor,},
                                ] }

          Counters are automatically created for all declared channels.
          The counter values are obtained from the internal data buffer (see STORE()).

        To write a custom program, basic methods are provided:

        - ATRIG(): send a signal (SIG_HARD_TRIG) to trigger registered callbacks
        - CLEAN(): empty the internal data buffer
        - STORE(): read the card channels values (using callbacks associated to channels)
          and store them in the internal data buffer:
          => '_channels_values[cname]' = [measure1, measure2, ...]
        
        
    """

    SIG_HARD_TRIG = "HARD_TRIG"

    def __init__(self, name, config):
        super().__init__(name, config)

        # monitor the musst-like program
        self._prg_task = None
        self._abort = False

        # register devices callbacks that will by called
        # when sending the fake hardware triggers
        self._registered_callbacks = []

        # buffer for data filled by program
        self._channels_values = {}

        self.load_config()

    def __del__(self):
        self._clean_cb_register()

    def load_config(self):
        self._card_channels = {}
        for cfg in self._config.get("channels"):
            chnum = cfg["channel"]
            rfunc = cfg["read_func"]
            cname = f"ch{chnum}"
            self._card_channels[cname] = (chnum, rfunc)
            self.create_counter(Counter, name=cname)

    def register_to_trigger_event(self, device):
        if hasattr(device, "on_trigger_event"):
            cb = device.on_trigger_event
            self._registered_callbacks.append(cb)
            levent.connect(self, self.SIG_HARD_TRIG, cb)

    def run_program(self, nb_triggers, delta_time):
        if not self._prg_task:
            self._abort = False
            self.CLEAN()
            self._prg_task = gevent.spawn(self.program, nb_triggers, delta_time)
        else:
            raise RuntimeError(f"program already running")

    def program(self, nb_triggers, delta_time):
        """ Here you can simulate a kind of musst program 
            Overload to write custom program.
            This method is called by the associated AcquitionMaster (see self.get_acquisition_object).

            This basic one just send 'nb_triggers' fake hardware triggers 
            via registered callbacks each 'delta_time'.
            
        """
        print("PROGRAM STARTS", nb_triggers, delta_time)
        _CLOCK.reset()

        for i in range(nb_triggers):
            print(f"=== CARD PROG: STORE AND ATRIG @trig {i}")
            self.STORE()
            self.ATRIG()
            gevent.sleep(delta_time)
            if self._abort:
                break

        print("PROGRAM FINISHED")

    def abort(self):
        if self.is_running:
            self._abort = True

    @property
    def is_running(self):
        return self._prg_task

    def ATRIG(self):
        self._send_trigger(self.SIG_HARD_TRIG)

    def STORE(self):
        # print("ON STORE")
        for cname in self._card_channels:
            chnum, rfunc = self._card_channels[cname]
            chvalue = rfunc()
            if self._channels_values.get(cname) is None:
                self._channels_values[cname] = [chvalue]
            else:
                self._channels_values[cname].append(chvalue)

    def CLEAN(self):
        self._channels_values = {}

    def get_values(self, from_index, *counters):
        cnts_values = []
        for cnt in counters:
            cnt_values = self._channels_values.get(cnt.name)
            if cnt_values is None:
                return [[]]
            cnts_values.append(cnt_values)

        dmin = min([len(values) for values in cnts_values])

        cnts_values = [values[from_index:dmin] for values in cnts_values]
        return cnts_values

    def read_all(self, *counters):
        self.STORE()
        cnts_value = []
        for cnt in counters:
            value = self._channels_values[cnt.name].pop(-1)
            cnts_value.append(value)

        return cnts_value

    def _send_trigger(self, signal):
        levent.send(self, signal)

    def _clean_cb_register(self):
        for cb in self._registered_callbacks:
            levent.disconnect(self, self.SIG_HARD_TRIG, cb)

    def _prepare_counters_data(self, npoints):
        pass


class FakeAcquisitionCardMaster(AcquisitionMaster):
    """ 
        AcquisitionMaster for the FakeAcquisitionCard to manage the card program that
        will sends fake hardware triggers and read/store the card channels data.
        
        This object is only necessary when working with devices in hardware trigger mode
        that preform measurements between scan iterations (like with a MotoMaster/Continuous scans)
    
    """

    def __init__(
        self,
        device,
        npoints=1,
        count_time=None,
        trigger_type=TRIGGER_MODE_ENUM.SOFTWARE,
        prepare_once=True,
        start_once=False,
        ctrl_params=None,
    ):

        super().__init__(
            device,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self._count_time = count_time
        self._start_epoch = None
        self._running_state = False
        # self._event = gevent.event.Event()

    def prepare(self):
        print("=== FakeAcquisitionCardMaster preparing")
        self.device.register_to_trigger_event(self.device)
        for slave in self.slaves:
            print(f"=== FakeAcquisitionCardMaster: registering {slave.device.name}")
            self.device.register_to_trigger_event(slave.device)
        print("=== FakeAcquisitionCardMaster prepared")

    def start(self):
        print("=== FakeAcquisitionCardMaster spawn program")
        self.device.run_program(self.npoints, self._count_time)

    def stop(self):
        print("=== FakeAcquisitionCardMaster stopping")
        if self.device.is_running:
            self.device.abort()
            self.wait_ready()
        print("=== FakeAcquisitionCardMaster stopped")

    # def trigger(self):
    #     print("=== FakeAcquisitionCardMaster trigger slaves")
    #     self.trigger_slaves()

    # def trigger_ready(self):
    #     return not self.device.is_running()

    def wait_ready(self):
        print("=== FakeAcquisitionCardMaster wait_ready starts")
        while self.device.is_running:
            gevent.sleep(0.02)
        print("=== FakeAcquisitionCardMaster wait_ready ends")


class XYSampleData:
    """ 
        Simulates a 2D sample. 
        Load an image as a numpy array and return the pixel value at position (x,y).

        Two motors (xmot, ymot) can be specified so that a call to get_pixel() will retreive
        the pixel value at motors positions: (int(xmot.position), int(ymot.position)).
        This simulates a sample positioned in space between (x=0, y=0) and (x=img.width, y=img.height).

        A specific location can be retrieve with get_pixel(x, y).
        If (x,y) is outside the image size, get_pixel returns the background value (self.bgval).
    
    """

    def __init__(self, fpath_or_array, xmot=None, ymot=None, scale=None, imshow=False):
        if isinstance(fpath_or_array, str):
            self.pil = file_to_pil(fpath_or_array).convert("L")

        elif isinstance(fpath_or_array, numpy.ndarray):
            self.pil = array_to_pil(fpath_or_array)

        self._xbin = 1
        self._ybin = 1
        self._bgval = 0

        self._xmot = xmot
        self._ymot = ymot

        self._xpos = 0
        self._ypos = 0

        if xmot:
            levent.connect(self._xmot, "position", self._on_update_xpos)
        if ymot:
            levent.connect(self._ymot, "position", self._on_update_ypos)

        if scale:
            self.rescale(scale)

        if imshow:
            disp = get_image_display(interactive=False)
            disp.show(self.array)

    def disconnect(self):
        levent.disconnect(self._xmot, "position", self._on_update_xpos)
        levent.disconnect(self._ymot, "position", self._on_update_ypos)

    def __del__(self):
        self.disconnect()

    @property
    def array(self):
        return pil_to_array(self.pil)

    @property
    def bgval(self):
        return self._bgval

    @bgval.setter
    def bgval(self, value):
        self._bgval = value

    def get_xpos(self):
        return self._xpos

    def get_ypos(self):
        return self._ypos

    def rescale(self, ratio):
        """ scale the image by the 'ratio' factor """
        ratio = abs(ratio)
        if ratio != 1:
            w, h = self.pil.size
            w = max(1, int(w * ratio))
            h = max(1, int(h * ratio))
            self.pil = self.pil.resize((w, h), 3)

    def get_pixel(self, x=None, y=None):
        if x is None:
            x = int(self.get_xpos())
        if y is None:
            y = int(self.get_ypos())

        if x < 0 or x >= self.pil.size[0] or y < 0 or y >= self.pil.size[1]:
            return self._bgval
        else:
            return self.pil.getpixel((x, y))

    def _on_update_xpos(self, value):
        self._xpos = value

    def _on_update_ypos(self, value):
        self._ypos = value


def simu_mesh(
    roby,
    robz,
    diode,
    size=(9, 9),
    start=(0, 0),
    scale=0.1,
    backnforth=True,
    imshow=True,
    simdatapath=None,
):

    """ Simulates a 2D mesh scan.
        - scale: a scale factor to apply to the 'sample image' (read from 'simu_card.ch3') (see scatter plot in Flint)
        - imshow: show the 'sample image' (the data source for 'simu_card.ch3'). 
          This image is the expected result of a scatter plot in Flint with
        { X: 'axis:roby', Y: 'axis:robz', V: 'simu_card.ch3' }

    """
    # --- fake controller
    fake_ctrl = FakeController("fake_ctrl")

    # --- simu card
    def read_diode():
        return diode.raw_read

    if simdatapath is None:
        simdatapath = test_image()
    img = XYSampleData(simdatapath, roby, robz, scale=scale, imshow=imshow)

    card_config = {
        "channels": [
            {"channel": 1, "read_func": img.get_xpos},
            {"channel": 2, "read_func": img.get_ypos},
            {"channel": 3, "read_func": img.get_pixel},
            {"channel": 4, "read_func": read_diode},
        ]
    }
    simu_card = FakeAcquisitionCard("simu_card", card_config)

    # --- scan
    xstop = start[0] + size[0] * 1
    ystop = start[1] + size[1] * 1
    s = amesh(
        roby,
        start[0],
        xstop,
        size[0] - 1,
        robz,
        start[1],
        ystop,
        size[1] - 1,
        0.01,
        fake_ctrl,
        simu_card,
        run=False,
        backnforth=backnforth,
    )
    print(s.acq_chain._tree)
    s.run()

    # to force cleaning now for pytest
    img.__del__()
    simu_card.__del__()


def simu_lscan(
    fast_motor,
    x_start,
    x_stop,
    x_intervals,
    count_time,
    *counters,
    save=True,
    save_images=False,
    backnforth=False,
    scale=0.1,
    imshow=True,
    simdatapath=None,
):
    """
        Simulates a fast scan (continuous scan along X).

        - scale: a scale factor to apply to the 'sample image' (read from 'simu_card.ch3') (see scatter plot in Flint)
        - imshow: show the 'sample image' (the data source for 'simu_card.ch3').
        
        usage example: 
          low res scan: s=simu_lscan(roby,5,20,100,0.1, backnforth=False, scale=0.2) 
          mid res scan: s=simu_lscan(roby,10,40,100,0.1, backnforth=False, scale=0.4) 
    """
    # test with:
    # s=simu_lscan(roby,5,20,100,0.1, backnforth=False, scale=0.2)

    # --- init scan parameters ---
    x_npoints = x_intervals + 1

    x_travel_time = count_time * x_intervals
    x_travel_distance = x_stop - x_start
    delta_x = x_travel_distance / x_intervals

    scan_params = {
        "count_time": count_time,
        "x_start": x_start,
        "x_stop": x_stop,
        "x_npoints": x_npoints,
        "delta_x": delta_x,
        "scan_dim": 1,
    }

    xoffset = 0  # delta_x/2
    positions = [x_start + i * delta_x - xoffset for i in range(0, x_npoints)]

    undershoot = None  # or 0

    # --- build the acquisition chain ---
    chain = AcquisitionChain()
    fast_master = MotorMaster(
        fast_motor,
        x_start,
        x_stop,
        time=x_travel_time,
        undershoot=undershoot,
        backnforth=backnforth,
    )

    # --- add a fake acquisition card that will send fake hardware triggers to children

    if simdatapath is None:
        simdatapath = test_image()
    img = XYSampleData(simdatapath, fast_motor, scale=scale, imshow=imshow)

    card_config = {
        "channels": [
            {"channel": 1, "read_func": img.get_xpos},
            {"channel": 2, "read_func": img.get_ypos},
            {"channel": 3, "read_func": img.get_pixel},
        ]
    }

    simu_card = FakeAcquisitionCard("simu_card", card_config)
    simu_card.trigger_type = TRIGGER_MODE_ENUM.HARDWARE  # TO DO HANDLE THIS BETTER

    simu_master = FakeAcquisitionCardMaster(
        simu_card,
        npoints=x_npoints,
        count_time=count_time,
        trigger_type=TRIGGER_MODE_ENUM.HARDWARE,
        prepare_once=True,
        start_once=False,
        ctrl_params=None,
    )

    chain.add(fast_master, simu_master)

    # ------ BUILDER for counters ----------------------------------------------

    # --- add a fake controller
    # cfg = {
    #     "counters": [
    #         {"counter_name": "fake0D", "data_size": (), "data_gen": "random"},
    #         {"counter_name": "fake1D", "data_size": 1024, "data_gen": 1},
    #     ]
    # }

    # fake_ctrl = FakeController("fake_ctrl", cfg)
    # fake_ctrl.trigger_type = TRIGGER_MODE_ENUM.HARDWARE  # TO DO HANDLE THIS BETTER

    # --- introspect
    counters = list(counters)
    # counters.append(fake_ctrl)
    counters.append(simu_card)
    builder = ChainBuilder(counters)

    for node in builder.get_nodes_by_controller_type(FakeController):
        if node.controller.trigger_type == TRIGGER_MODE_ENUM.HARDWARE:
            node.set_parameters(
                acq_params={"npoints": x_npoints, "count_time": count_time}
            )
            chain.add(simu_master, node)

    print(chain._tree)
    builder.print_tree(not_ready_only=False)

    total_points = x_npoints

    simu_card._counters["ch1"].fullname

    fast_axis_name = simu_card._counters["ch1"].fullname  # f"axis:{fast_motor.name}"
    slow_axis_name = simu_card._counters["ch2"].fullname  # f"axis:{slow_motor.name}"

    scan_info_dict = {
        "npoints": total_points,
        "type": "lscan",
        "count_time": count_time,
        "data_dim": 1,
        "start": x_start - xoffset,
        "stop": x_stop - xoffset,
    }

    scan_info = ScanInfo()
    scan_info.update(scan_info_dict)

    scan_info.set_channel_meta(
        fast_axis_name,
        # The group have to be the same for all this channels
        group="g1",
        # This is the fast axis
        axis_id=0,
        # In forth direction only
        axis_kind="forth",
        # The grid have to be specified
        start=x_start - xoffset,
        stop=x_stop - xoffset,
        axis_points=x_npoints,
        # Optionally the full number of points can be specified
        points=total_points,
    )

    cnt_name = "simu_card:ch3"  # 'fake_ctrl:fake0D'
    scan_info.set_channel_meta(cnt_name, group="g1")
    # scan_info.set_channel_meta('fake_ctrl:fake1D', group="g1")

    command_line = (
        f"lscan {fast_motor.name} {x_start} {x_stop} {x_intervals} {count_time}"
    )
    sc = Scan(
        chain,
        name=command_line,
        scan_info=scan_info,
        save=save,
        save_images=save_images,
        scan_saving=None,
        # data_watch_callback=StepScanDataWatch(),
    )

    sc.run()

    # to force cleaning now for pytest
    img.__del__()
    simu_card.__del__()

    return sc


def simu_l2scan(
    fast_motor,
    x_start,
    x_stop,
    x_intervals,
    slow_motor,
    y_start,
    y_stop,
    y_intervals,
    count_time,
    *counters,
    save=True,
    save_images=False,
    backnforth=False,
    scale=0.1,
    imshow=True,
    simdatapath=None,
):
    """
        Simulates a Zap scan (continuous scan along X and step_by_step along Y).

        - scale: a scale factor to apply to the 'sample image' (read from 'simu_card.ch3') (see scatter plot in Flint)
        - imshow: show the 'sample image' (the data source for 'simu_card.ch3'). 
          This image is the expected result of a scatter plot in Flint with
          { X: 'simu_card.ch1', Y: 'simu_card.ch2', V: 'simu_card.ch3' }
        

        usage example: 
          low res scan: s=simu_l2scan(roby,5,20,100,robz,10,20,10,0.1, backnforth=False, scale=0.2) 
          mid res scan: s=simu_l2scan(roby,10,40,100,robz,20,40,20,0.1, backnforth=False, scale=0.4) 
    """
    # test with:
    # s=simu_l2scan(roby,5,20,100,robz,10,20,10,0.1, backnforth=False, scale=0.2)

    # --- init scan parameters ---
    x_npoints = x_intervals + 1
    y_npoints = y_intervals + 1

    x_travel_time = count_time * x_intervals
    x_travel_distance = x_stop - x_start
    delta_x = x_travel_distance / x_intervals

    y_travel_time = x_travel_time * y_npoints
    y_travel_distance = y_stop - y_start
    delta_y = y_travel_distance / y_intervals

    scan_params = {
        "count_time": count_time,
        "x_start": x_start,
        "x_stop": x_stop,
        "x_npoints": x_npoints,
        "delta_x": delta_x,
        "y_start": y_start,
        "y_stop": y_stop,
        "y_npoints": y_npoints,
        "delta_y": delta_y,
        "scan_dim": 2,
    }

    xoffset = 0  # delta_x/2
    positions = [x_start + i * delta_x - xoffset for i in range(0, x_npoints)]

    undershoot = None  # or 0

    # --- build the acquisition chain ---
    chain = AcquisitionChain()
    fast_master = MotorMaster(
        fast_motor,
        x_start,
        x_stop,
        time=x_travel_time,
        undershoot=undershoot,
        backnforth=backnforth,
    )

    slow_master = LinearStepTriggerMaster(y_npoints, slow_motor, y_start, y_stop)

    chain.add(slow_master, fast_master)

    # --- add a fake acquisition card that will send fake hardware triggers to children

    if simdatapath is None:
        simdatapath = test_image()
    img = XYSampleData(simdatapath, fast_motor, slow_motor, scale=scale, imshow=imshow)

    card_config = {
        "channels": [
            {"channel": 1, "read_func": img.get_xpos},
            {"channel": 2, "read_func": img.get_ypos},
            {"channel": 3, "read_func": img.get_pixel},
        ]
    }

    simu_card = FakeAcquisitionCard("simu_card", card_config)
    simu_card.trigger_type = TRIGGER_MODE_ENUM.HARDWARE  # TO DO HANDLE THIS BETTER

    simu_master = FakeAcquisitionCardMaster(
        simu_card,
        npoints=x_npoints,
        count_time=count_time,
        trigger_type=TRIGGER_MODE_ENUM.HARDWARE,
        prepare_once=True,
        start_once=False,
        ctrl_params=None,
    )

    chain.add(fast_master, simu_master)

    # ------ BUILDER for counters ----------------------------------------------

    # --- add a fake controller
    cfg = {
        "counters": [
            {"counter_name": "fake0D", "data_size": (), "data_gen": "random"},
            {"counter_name": "fake1D", "data_size": 1024, "data_gen": 1},
        ]
    }

    fake_ctrl = FakeController("fake_ctrl", cfg)
    fake_ctrl.trigger_type = TRIGGER_MODE_ENUM.HARDWARE  # TO DO HANDLE THIS BETTER

    # --- introspect
    counters = list(counters)
    counters.append(fake_ctrl)
    counters.append(simu_card)
    builder = ChainBuilder(counters)

    for node in builder.get_nodes_by_controller_type(FakeController):
        if node.controller.trigger_type == TRIGGER_MODE_ENUM.HARDWARE:
            node.set_parameters(
                acq_params={"npoints": x_npoints, "count_time": count_time}
            )
            chain.add(simu_master, node)
        else:
            node.set_parameters(
                acq_params={"npoints": y_npoints, "count_time": count_time}
            )
            chain.add(slow_master, node)

    for node in builder.get_nodes_by_controller_type(SamplingCounterController):
        node.set_parameters(acq_params={"npoints": y_npoints, "count_time": count_time})
        chain.add(slow_master, node)

    print(chain._tree)
    builder.print_tree(not_ready_only=False)

    total_points = x_npoints * y_npoints

    simu_card._counters["ch1"].fullname

    fast_axis_name = simu_card._counters["ch1"].fullname  # f"axis:{fast_motor.name}"
    slow_axis_name = simu_card._counters["ch2"].fullname  # f"axis:{slow_motor.name}"

    scan_info_dict = {
        "npoints": total_points,
        "npoints1": x_npoints,
        "npoints2": y_npoints,
        "type": "l2scan",
        "count_time": count_time,
        "data_dim": 2,
        "start": [y_start, x_start - xoffset],
        "stop": [y_stop, x_stop - xoffset],
    }

    scan_info = ScanInfo()
    scan_info.update(scan_info_dict)

    scan_info.set_channel_meta(
        fast_axis_name,
        # The group have to be the same for all this channels
        group="g1",
        # This is the fast axis
        axis_id=0,
        # In forth direction only
        axis_kind="forth",
        # The grid have to be specified
        start=x_start - xoffset,
        stop=x_stop - xoffset,
        axis_points=x_npoints,
        # Optionally the full number of points can be specified
        points=total_points,
    )

    scan_info.set_channel_meta(
        slow_axis_name,
        group="g1",
        axis_id=1,
        axis_kind="forth",
        start=y_start,
        stop=y_stop,
        axis_points=y_npoints,
        points=total_points,
    )

    cnt_name = "simu_card:ch3"  # 'fake_ctrl:fake0D'
    scan_info.set_channel_meta(cnt_name, group="g1")
    # scan_info.set_channel_meta('fake_ctrl:fake1D', group="g1")

    # Request a specific scatter to be displayed
    scan_info.add_scatter_plot(x=fast_axis_name, y=slow_axis_name, value=cnt_name)

    command_line = f"l2scan {fast_motor.name} {x_start} {x_stop} {x_intervals} "
    command_line += f"{slow_motor.name} {y_start} {y_stop} {y_intervals} {count_time}"

    sc = Scan(
        chain,
        name=command_line,
        scan_info=scan_info,
        save=save,
        save_images=save_images,
        scan_saving=None,
        # data_watch_callback=StepScanDataWatch(),
    )

    sc.run()

    # to force cleaning now for pytest
    img.__del__()
    simu_card.__del__()

    return sc
