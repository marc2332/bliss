# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ESRF - Simulink controller

Example YAML_ configuration:

.. code-block:: yaml

    plugin: bliss      # (1)
    class: simulink    # (2)
    name: goat1        # (3)
    url: pcmel1        # (4)


1. use the *bliss* plugin (mandatory, inherited)
2. simulink class (mandatory, inherited)
3. name (mandatory)
4. URL: the 0RPC address (ex: tcp://pcmel1:8200)
  * if simple host name or IP is given, it assumes 'tcp://' protocol and
    port 8001 (in the above example the string 'pcmel1' is interpreted
    as 'tcp://pcmel1:8200')


Usage::

    >>> from bliss.config.static import get_config()
    >>> config = get_config()

    >>> goat = config.get('goat1')

Found in a box named "counters"
Names are counter_<qqchose>
counters/
counters/counter_FPGA1_SSIM1/Signal(cnt) : raw value (READ_ONLY)
counters/counter_FPGA1_SSIM1/offset(cnt) 
counters/counter_FPGA1_SSIM1/count2unit 
counters/counter_FPGA1_SSIM1/switch_correction 
counters/counter_FPGA1_SSIM1/Unit : calculated value (offset, cnt2unit) without correction
counters/counter_FPGA1_SSIM1/Corrected_value : calculated value + correction

1-20: (IN + offset) * steps_per_unit - correction if active
      (IN + offset(cnt)) * count2unit - correctyion if active (switch_correction)
1 : xtal 1 - 311 : atto ur
2 : xtal 1 - 311 : atto h
3 : xtal 1 - 311 : atto dr

4 : xtal 1 - 111 : atto uh
5 : xtal 1 - 111 : atto r
6 : xtal 1 - 111 : atto dh

7 : xtal 2 - 311 : atto ur
8 : xtal 2 - 311 : atto h
9 : xtal 2 - 311 : atto dr

10 : xtal 2 - 111 : atto uh
11 : xtal 2 - 111 : atto r
12 : xtal 2 - 111 : atto dh

13 : frame : atto u
14 : frame : atto dh
15 : frame : atto dr

16 : bragg

17 : empty
18 : empty
19 : empty
20 : empty

21 : xtal 1 - 311 - z = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
22 : xtal 1 - 311 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
23 : xtal 1 - 311 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)

24 : xtal 1 - 111 - z = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
25 : xtal 1 - 111 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
26 : xtal 1 - 111 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
27 : xtal 2 - 311 - z = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
28 : xtal 2 - 311 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
29 : xtal 2 - 311 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
30 : xtal 2 - 111 - z = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
31 : xtal 2 - 111 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
32 : xtal 2 - 111 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
33 : frame - z = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
34 : frame - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
35 : frame - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
36 : xtal 311 - dz = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
37 : xtal 311 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
38 : xtal 311 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
39 : xtal 111 - dz = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
40 : xtal 111 - ry = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
41 : xtal 111 - rx = (val+offset(cnt)) * count2unit - correction if active (switch_correction)
"""

import enum
import logging
import weakref
import functools
import collections
import numpy as np
import gevent
import treelib
from bliss.comm import rpc
from bliss.common.counter import Counter, SamplingCounter
from bliss.controllers.counter import CounterController
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave

##########################################################################
##########                                                      ##########
##########                 Speedgoat Defines                    ##########
##########                                                      ##########
##########################################################################
class ScopeType(enum.IntEnum):
    Null = 0
    Host = 1
    Target = 2
    File = 3
    Hidden = 4


class TriggerMode(enum.IntEnum):
    FreeRun = 0
    Software = 1
    Signal = 2
    Scope = 3
    ScopeEnd = 4


class TriggerSlope(enum.IntEnum):
    Either = 0
    Rising = 1
    Falling = 2


class ScopeMode(enum.IntEnum):
    Numerical = 0
    Redraw = 1
    Sliding = 2
    Rolling = 3


class ScopeState(enum.IntEnum):
    WaitToStart = 0
    WaitForTrigger = 1
    Acquiring = 2
    Finished = 3
    Interrupted = 4
    PreAcquiring = 5


class RegulState(enum.IntEnum):
    Off = 0
    On = 1
    Error = 2


class LogMode(enum.IntEnum):
    Time = 0
    Value = 1


# The following enums are not coming from simulink.
# They are conventions agreed with mechatronics for the several interfaces


class MotionTriggerMode(enum.IntEnum):
    Internal = 1
    Software = 2
    Hardware = 3


class MotionSetPointMode(enum.IntEnum):
    Internal = 1
    Software = 2


class MotionStartMode(enum.IntEnum):
    Direct = 1  # motion is started when setPoint param in written
    Triggered = 2  # motion is started by controller moveTrigger


##########################################################################
##########                                                      ##########
##########               Speedgoat Basic Objects                ##########
##########                                                      ##########
##########################################################################
class BlockMixin(object):
    def _get_param(self, name):
        return self.speedgoat.params[self._block + "/" + name]

    def _set_param(self, name, value):
        self.speedgoat.params[self._block + "/" + name] = value

    def _get_signal(self, name):
        return self.speedgoat.signals[self._block + "/" + name]


##########################################################################
##########                                                      ##########
##########             Speedgoat Connexions Tools               ##########
##########                                                      ##########
##########################################################################


def _to_host_port(url, default_port=None):
    pars = url.rsplit(":", 1) if isinstance(url, str) else url
    port = int(pars[1]) if len(pars) > 1 else default_port
    return pars[0], port


def _to_zerorpc_url(url, default_port=None):
    host, port = _to_host_port(url, default_port)
    if "://" not in host:
        host = "tcp://" + host
    return "{}:{}".format(host, port)


##########################################################################
##########                                                      ##########
##########                  Speedgoat Tree Tools                ##########
##########                                                      ##########
##########################################################################

Node = lambda: collections.defaultdict(Node)


def create_block_dict(infos):
    """
    A dictionary of blocks. Key is block name and value is a parameter/signal
    dictionary.
    """
    blocks = collections.defaultdict(dict)
    for info in infos:
        blocks[info["block"]][info["name"]] = info
    return blocks


def create_tree(infos, param_leaf=True):
    """infos: obtained from speedgoat.get_param_infos()
              or speedgoat.get_signal_infos()
    """
    tree = treelib.Tree()
    root = tree.create_node("", "")
    for block, params in create_block_dict(infos).items():
        parent, block_path = root, []
        for item in block.split("/"):
            if item:
                block_path.append(item)
            block_name = "/".join(block_path)
            node = tree.get_node(block_name)
            if node is None:
                node = tree.create_node(item, block_name, parent)
            parent = node
        for param_name, param_info in params.items():
            puid = "{}/{}".format(param_info["block"], param_info["name"])
            param_node = tree.create_node(param_name, puid, parent, param_info)
            if not param_leaf:
                for pname, pvalue in param_info.items():
                    piuid = puid + "." + pname
                    pilabel = "{} = {}".format(pname, pvalue)
                    tree.create_node(pilabel, piuid, param_node, pvalue)
    return tree


##########################################################################
##########                                                      ##########
##########                Speedgoat Introspection               ##########
##########                                                      ##########
##########################################################################


def is_ring_buffer_node(tree, node):
    has_dim, has_size = False, False
    for child in tree.children(node.identifier):
        if child.tag == "ringBufferDim":
            has_dim = True
        elif child.tag == "ringBufferSize":
            has_size = True
    return has_dim and has_size


##########################################################################
##########                                                      ##########
##########           Speedgoat Data Acquisition Objects         ##########
##########                                                      ##########
##########################################################################


class FastDAQ(object):
    def __init__(self, speedgoat, scope):

        self.speedgoat = speedgoat
        self.scope = scope

    #
    # buffer
    #
    def set_counters(self, counter_list):
        signal_list = []
        for counter in counter_list:
            signal_list.append(counter.index())

        self.set_signals(signal_list)

    def set_signals(self, signal_list):
        nb_signals = len(signal_list)
        if nb_signals > 20:
            raise ValueError(
                "Nb signals {} exceeds maximum ({})".format(nb_signals, 20)
            )

        self._signal_list = signal_list
        sp_signal_list = np.full((20,), 1)
        for idx in range(len(self._signal_list)):
            sp_signal_list[idx] = self._signal_list[idx]

        self.speedgoat.params["select_data/selectVector/Value"] = sp_signal_list

    #
    # Fast Scope
    #
    def start_fast_acquisition(self, frequency, nb_samples, counter_list):
        self.scope.stop()
        gevent.sleep(0.1)

        if frequency > 0:
            self.scope.decimation = int(0.5 + (10000.0 / frequency))
        else:
            return

        if nb_samples > 0 and nb_samples <= 2000000:
            self.scope.num_samples = nb_samples
        else:
            return

        self.set_counters(counter_list)

        self.scope.start()
        self.speedgoat.set_param("fastDaqTrigger/Value", 0)
        self.speedgoat.set_param("fastDaqTrigger/Value", 1)

    @property
    def acq_frequency(self):
        return 10000.0 / self.scope.decimation

    @acq_frequency.setter
    def acq_frequency(self, freq):
        if freq > 0:
            self.scope.decimation = int(0.5 + (10000.0 / freq))

    @property
    def acq_nb_samples(self):
        return self.scope.num_samples

    @acq_nb_samples.setter
    def acq_nb_samples(self, nb_samples):
        if nb_samples > 0 and nb_samples <= 2000000:
            self.scope.num_samples = nb_samples

    def start(self):
        self.scope.start()
        self.speedgoat.set_param("fastDaqTrigger/Value", 0)
        self.speedgoat.set_param("fastDaqTrigger/Value", 1)

    #
    # Scope
    #

    def scope_stop(self):
        self.scope.stop()

    def scope_start(self):
        self.scope.start()

    def scope_state(self):
        self.scope.state()

    def scope_read_is_finish(self):
        return self.scope.state == ScopeState.Finished

    def scope_get_data(self):
        signals = self.scope.signal_list
        data_arr = []
        for signal in signals:
            data_arr.append((signal, self.scope.get_data(signal, 0, None, 1)))
        return data_arr


class DAQ(object):
    def __init__(self, speedgoat, scope):

        self.speedgoat = speedgoat
        self.scope = scope

    #
    # ring buffer
    #
    def ringbuffer_set_counters(self, counter_list):
        signal_list = []
        for counter in counter_list:
            signal_list.append(counter.index())

        self.ringbuffer_set_signals(signal_list)

    def ringbuffer_set_signals(self, signal_list):
        nb_signals = len(signal_list)
        if nb_signals > self.ringbuffer_max_signals:
            raise ValueError(
                "Nb signals {} exceeds maximum ({})".format(
                    nb_signals, self.ring_buffer_max_signals
                )
            )

        self._signal_list = signal_list
        sp_signal_list = np.full((20,), 1)
        for idx in range(len(self._signal_list)):
            sp_signal_list[idx] = self._signal_list[idx]

        self.speedgoat.params[
            "select_data_ringBuffer/selectVector/Value"
        ] = sp_signal_list

    def ringbuffer_empty(self):
        nb_no_read = self.daq_points_acquired()
        if nb_no_read > 0:
            data = self.scope_read(nb_no_read)

    @property
    def ringbuffer_max_signals(self):
        return int(
            self.speedgoat.params["statusBuffer/internRingbuffer/ringBufferSize"]
        )

    @property
    def ringbuffer_point_to_read(self):
        int(self.speedgoat.params["nbReadSamples/Value"])

    @ringbuffer_point_to_read.setter
    def ringbuffer_point_to_read(self, val):
        self.speedgoat.params["nbReadSamples/Value"] = val

    #
    # Scope
    #
    def scope_stop(self):
        self.scope.stop()

    def scope_start(self):
        self.scope.start()

    def scope_state(self):
        self.scope.state()

    @property
    def scope_point_to_read(self):
        self.scope.num_samples

    @scope_point_to_read.setter
    def scope_point_to_read(self, nb_read_points):
        self.scope.num_samples = nb_read_points

    def scope_read_start(self):
        self.speedgoat.params["readRingBuffer/Value"] = 0
        while int(self.speedgoat.params["readRingBuffer/Value"]) != 0:
            gevent.sleep(0.001)  # 1ms
        self.speedgoat.params["readRingBuffer/Value"] = 1
        while int(self.speedgoat.params["readRingBuffer/Value"]) != 1:
            gevent.sleep(0.001)  # 1ms

    def scope_read_is_finish(self):
        return self.scope.state == ScopeState.Finished

    def scope_read(self, nbpoint):
        # print("Speedgoat: Scope stop")
        self.scope_stop()
        # print("Speedgoat: RingBuffer point to read")
        self.ringbuffer_point_to_read = nbpoint
        # print("Speedgoat: Scope Scope point to read")
        self.scope_point_to_read = nbpoint
        # print("Speedgoat: Scope start")
        self.scope_start()
        # print("Speedgoat: Scope read start")
        self.scope_read_start()
        # print(f"Speedgoat: Scope wait read finish {self.scope.state}")
        nbpass = 0
        read_success = True
        while (not self.scope_read_is_finish()) and (nbpass < 100):
            gevent.sleep(1.1 * nbpoint * 0.0001)
            nbpass = nbpass + 1
            if nbpass == 100:
                read_success = False
        if read_success:

            # print("Speedgoat: Scope get_data", end=" ... ")
            data = self.scope_get_data()
            # print("Done")

            return_data = np.zeros((len(self._signal_list), nbpoint))
            for i in range(len(self._signal_list)):
                return_data[i] = data[i][1]

            # print("Speedgoat: readRingBuffer/Value", end=" ... ")
            self.speedgoat.params["readRingBuffer/Value"] = 0
            # print("Done")

            return np.transpose(return_data)
        else:
            # print("Speedgoat: READ FAILED, RETRY")
            return None

    def scope_get_data(
        self, signals=None, first_point=0, num_samples=None, decimation=1
    ):
        if signals is None:
            signals = self.scope.signal_list

        data_arr = []
        for signal in signals:
            # print(f"\n{signal}, {first_point}, {decimation}")
            data_arr.append(
                (
                    signal,
                    self.scope.get_data(signal, first_point, num_samples, decimation),
                )
            )

        return data_arr

        # return [
        #    (signal, self.scope.get_data(signal, first_point, num_samples, decimation))
        #    for signal in signals
        # ]

    #
    # daq (interface to outside world)
    #
    def daq_prepare(self, counter_list, nb_point):
        # print("Enter daq_prepare", end=" ... ")
        self.ringbuffer_set_counters(counter_list)
        self.ringbuffer_empty()
        self.point_to_acq = nb_point
        self.last_index = (
            int(self.speedgoat.signals["statusBuffer/saveIndex"]) + nb_point
        )
        if self.last_index > 50000:
            self.last_index = self.last_index - 50000
        # print("Done")

    def daq_points_acquired(self):
        return int(self.speedgoat.signals["statusBuffer/numberOfSamples"])

    def daq_is_finished(self):

        if int(self.speedgoat.signals["statusBuffer/saveIndex"]) == self.last_index:
            return True

        return False


##########################################################################
##########                                                      ##########
##########                     Speedgoat Counters               ##########
##########                                                      ##########
##########################################################################


def is_counters_controller_node(tree, node):
    if node.tag == "counters":
        return True

    return False


class SpeedgoatCountersController(CounterController):
    def __init__(self, speedgoat, signal_node, param_node):
        self.speedgoat = speedgoat
        self.signal_node = signal_node
        self.param_node = param_node

        super().__init__(self.speedgoat.name)  # + "CC")

        # build counter signal list
        sig_cnt = {}
        tree = self.speedgoat._cache["signal_tree"]
        for s_node in tree.children(signal_node.identifier):
            if s_node.tag.split("_")[0] == "counter":
                s_name = s_node.tag[8:]
                sig_cnt[s_name] = s_node

        # build counter param list
        par_cnt = {}
        tree = self.speedgoat._cache["param_tree"]
        for p_node in tree.children(param_node.identifier):
            if p_node.tag.split("_")[0] == "counter":
                p_name = p_node.tag[8:]
                par_cnt[p_name] = p_node

        # remove cnt not in sig and par
        for cnt in sig_cnt.keys():
            if cnt not in par_cnt:
                sig_cnt.pop(cnt)
        for cnt in par_cnt.keys():
            if cnt not in sig_cnt:
                par_cnt.pop(cnt)

        # create counters
        for cnt_name in sig_cnt.keys():
            self.create_counter(
                SpeedgoatCounter, cnt_name, sig_cnt[cnt_name], par_cnt[cnt_name]
            )

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):

        trigger_type = acq_params.pop("trigger_type")

        if trigger_type == "HARDWARE":

            from bliss.scanning.acquisition.speedgoat import SpeedgoatAcquisitionSlave

            acq_params.pop(
                "count_time"
            )  # remove the count_time used in the other case for the SamplingCounterAcquisitionSlave  (i.e. if trigger_type != "HARDWARE" )
            return SpeedgoatAcquisitionSlave(
                self, ctrl_params=ctrl_params, **acq_params
            )
        else:
            return SamplingCounterAcquisitionSlave(
                self, ctrl_params=ctrl_params, **acq_params
            )

    def get_default_chain_parameters(self, scan_params, acq_params):
        try:
            count_time = acq_params["count_time"]
        except KeyError:
            count_time = scan_params["count_time"]

        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        trigger_type = acq_params.get("trigger_type", "SOFTWARE")

        params = {
            "count_time": count_time,
            "npoints": npoints,
            "trigger_type": trigger_type,
        }

        return params

    def read_counters(self, counter_list_name):
        # return list of values
        idx_list = []
        for name in counter_list_name:
            idx_list.append(getattr(self.counters, name).read_index())

        value_list = self.speedgoat.get_signal_value_from_idxs(idx_list)

        return value_list

    def read_all(self, *counters):
        cnt_names = [cnt.name.replace(self.name + ".", "") for cnt in counters]
        return self.read_counters(cnt_names)


class SpeedgoatCounter(SamplingCounter):
    def __init__(self, counter_name, signal_node, param_node, controller):
        super().__init__(counter_name, controller)

        self.signal_node = signal_node
        self.param_node = param_node

        self.signals = {}
        for node in self.speedgoat._cache["signal_tree"].children(
            self.signal_node.identifier
        ):
            if node.data is not None:
                self.signals[node.tag] = node

    @property
    def speedgoat(self):
        return self._counter_controller.speedgoat

    def read_signal(self, signal):
        if signal in self.signals.keys():
            idx = self.signals[signal].data["idx"]
            value = self.speedgoat.get_signal_value_from_idxs([idx])
        return value[0]

    def read_index(self):
        return self.signals["Unit"].data["idx"]

    def read(self):
        return self.read_signal("Unit")

    def index(self):
        return self.read_signal("CounterIndex")

    def tree_name(self):
        return self.signal_node.identifier


##########################################################################
##########                                                      ##########
##########                        Regulation                    ##########
##########                                                      ##########
##########################################################################
class Regul(object):
    def __init__(self, speedgoat):
        self.speedgoat = speedgoat

    def set_frame_correction(self, onoff):
        ssi_name = []
        for i in range(10):
            name = "plant/counters/counter_FPGA1_SSIM%d/correction_OnOff/Value" % (
                i + 1
            )
            self.set_param(name, onoff)
        for i in range(5):
            name = "plant/counters/counter_FPGA2_SSIM%d/correction_OnOff/Value" % (
                i + 1
            )
            self.set_param(name, onoff)

    def reset_interf(self):

        ssim_val = self.read_interf()

        for i in range(10):
            count2unit = self.get_param(
                "plant/counters/counter_FPGA1_SSIM%d/count2unit/Gain" % (i + 1)
            )
            corr_name = "plant/counters/counter_FPGA1_SSIM%d/correction_switch" % (
                i + 1
            )
            corr_val = int(self.get_signal(corr_name) / count2unit)
            param = "plant/counters/counter_FPGA1_SSIM%d/offset(cnt)/Bias" % (i + 1)
            self.set_param(param, (corr_val - ssim_val[i]))
        for i in range(5):
            count2unit = self.get_param(
                "plant/counters/counter_FPGA2_SSIM%d/count2unit/Gain" % (i + 1)
            )
            corr_name = "plant/counters/counter_FPGA2_SSIM%d/correction_switch" % (
                i + 1
            )
            corr_val = int(self.get_signal(corr_name) / count2unit)
            param = "plant/counters/counter_FPGA2_SSIM%d/offset(cnt)/Bias" % (i + 1)
            self.set_param(param, (corr_val - ssim_val[i + 10]))

    def read_interf(self):
        ssim_val = []
        for i in range(10):
            signal = "plant/counters/counter_FPGA1_SSIM%d/Signal(cnt)" % (i + 1)
            ssim_val.append(self.get_signal(signal))
        for i in range(5):
            signal = "plant/counters/counter_FPGA2_SSIM%d/Signal(cnt)" % (i + 1)
            ssim_val.append(self.get_signal(signal))

        return ssim_val

    def reset_xtal_dz(self, value):
        if value > 0:
            self.set_param(
                "plant/counters/counter_xtal_111_dz/offset(cnt)/Bias", value * 1000000
            )
            # Added by Maxim to test the regulation on the xtal_311 interferometer set
            self.set_param(
                "plant/counters/counter_xtal_311_dz/offset(cnt)/Bias", value * 1000000
            )

    def state(self):
        loop_error = int(self.get_signal("Regulator/controler_error_status"))
        if loop_error:
            state = RegulState.Error
        else:
            regul_state = int(self.get_param("closedLoop_OnOff/Value"))
            if regul_state:
                state = RegulState.On
            else:
                state = RegulState.Off

        return state

    def setOn(self):
        if self.state() == RegulState.Error:
            self.set_param("closedLoop_OnOff/Value", 0)
            self.set_param("Regulator/resetError/Value", 1)
            self.set_param("Regulator/resetError/Value", 0)

        self.set_param("Regulator/Regulator_P/Gain", 1)
        self.set_param("closedLoop_OnOff/Value", 1)

    def setOff(self):
        self.set_param("closedLoop_OnOff/Value", 0)
        if self.state() == RegulState.Error:
            self.set_param("Regulator/resetError/Value", 0)
            self.set_param("Regulator/resetError/Value", 1)
            self.set_param("Regulator/resetError/Value", 0)

    def setPolynom(self, angle, a, b, c):
        if angle == "rx":
            var_name_a = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/a/Value"
            )
            var_name_b = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/b/Value"
            )
            var_name_c = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/c/Value"
            )
        elif angle == "ry":
            var_name_a = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/a/Value"
            )
            var_name_b = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/b/Value"
            )
            var_name_c = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/c/Value"
            )
        else:
            print('Correct angle are "rx" or "ry", exit !!!')
            return

        self.set_param(var_name_a, a)
        self.set_param(var_name_b, b)
        self.set_param(var_name_c, c)

    def getPolynom(self, angle):
        if angle == "rx":
            var_name_a = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/a/Value"
            )
            var_name_b = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/b/Value"
            )
            var_name_c = (
                "plant/counters/counter_xtal_111_drx/2nd-order-correction(unit)/c/Value"
            )
        elif angle == "ry":
            var_name_a = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/a/Value"
            )
            var_name_b = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/b/Value"
            )
            var_name_c = (
                "plant/counters/counter_xtal_111_dry/2nd-order-correction(unit)/c/Value"
            )
        else:
            print('Correct angle are "rx" or "ry", exit !!!')
            return None

        return (
            self.get_param(var_name_a),
            self.get_param(var_name_b),
            self.get_param(var_name_c),
        )

    def usePolynom(self, state):
        var_name = "plant/counters/counter_xtal_111_dry/correction_OnOff/Value"
        self.set_param(var_name, state)
        var_name = "plant/counters/counter_xtal_111_drx/correction_OnOff/Value"
        self.set_param(var_name, state)

    def usePolynomGet(self):
        var_name = "plant/counters/counter_xtal_111_dry/correction_OnOff/Value"
        ry = self.get_param(var_name)
        var_name = "plant/counters/counter_xtal_111_drx/correction_OnOff/Value"
        rx = self.get_param(var_name)

        return (ry, rx)

    def set_param(self, param, value):
        self.speedgoat.params[param] = value
        ret_val = self.speedgoat.params[param]
        while self.get_param(param) != value:
            gevent.sleep(0.00001)  # 10us

    def get_param(self, param):
        return self.speedgoat.params[param]

    def get_signal(self, signal):
        return self.speedgoat.signals[signal]


##########################################################################
##########                                                      ##########
##########                     Speedgoat Motors                 ##########
##########                                                      ##########
##########################################################################


def is_motors_controller_node(tree, node):
    if node.tag == "Motors":
        return True

    return False


class MotorsController(object):
    def __init__(self, speedgoat, signal_node, param_node):
        self.select_value = {
            "fjpur": 0,
            "fjpuh": 0,
            "fjpd": 0,
            "dz": 1,
            "dry": 2,
            "drx": 3,
        }
        self.speedgoat = speedgoat
        self.signal_node = signal_node
        self.param_node = param_node

        self.name = self.speedgoat.name + "_motors_controller"

        # build motor signal list
        sig_mot = {}
        tree = self.speedgoat._cache["signal_tree"]
        for s_node in tree.children(signal_node.identifier):
            if s_node.tag.split("_")[0] == "motor":
                s_name = s_node.tag[6:]
                sig_mot[s_name] = s_node

        # build motor param list
        par_mot = {}
        tree = self.speedgoat._cache["param_tree"]
        for p_node in tree.children(param_node.identifier):
            if p_node.tag.split("_")[0] == "motor":
                p_name = p_node.tag[6:]
                par_mot[p_name] = p_node

        # remove motor not in sig and par
        for mot in sig_mot.keys():
            if mot not in par_mot:
                sig_mot.pop(mot)
        for mot in par_mot.keys():
            if mot not in sig_mot:
                par_mot.pop(mot)

        # create counters
        self.available_motors = {}
        for mot_name in sig_mot.keys():
            self.available_motors[mot_name] = Motor(
                self,
                mot_name,
                sig_mot[mot_name],
                par_mot[mot_name],
                self.select_value[mot_name],
            )

    def is_available_motor(self, motor_name):
        if motor_name in self.available_motors.keys():
            return True
        else:
            return False


class Motor(object):
    def __init__(self, controller, name, signal_node, param_node, select_value):
        self.controller = controller
        self.name = name
        self.signal_node = signal_node
        self.param_node = param_node
        self.sel_value = select_value

    def set_param(self, param, value):
        param_to_read = "Motors/motor_%s/%s" % (self.name, param)
        self.controller.speedgoat.params[param_to_read] = value
        while self.get_param(param) != value:
            gevent.sleep(0.00001)  # 10us

    def get_param(self, param):
        param_to_read = "Motors/motor_%s/%s" % (self.name, param)
        return self.controller.speedgoat.params[param_to_read]

    def get_signal(self, signal):
        signal_to_read = "Motors/motor_%s/%s" % (self.name, signal)
        return self.controller.speedgoat.signals[signal_to_read]

    @property
    def position(self):
        return float(self.get_signal("ReadPosition"))

    @property
    def is_moving(self):
        return int(self.get_signal("isMoving"))

    @property
    def acc_time(self):
        return float(self.get_param("accelTime/Value"))

    @acc_time.setter
    def acc_time(self, accel_time):
        self.set_param("accelTime/Value", accel_time)

    @property
    def velocity(self):
        return float(self.get_param("velocity/Value"))

    @velocity.setter
    def velocity(self, velocity):

        self.set_param("velocity/Value", velocity)

    @property
    def set_point(self):
        return self.get_param("setPoint/Value")

    @set_point.setter
    def set_point(self, position):
        self.set_param("setPoint/Value", position)

    def prepare_move(self):
        self.controller.speedgoat.params[
            "Motors/selectPseudoMotor/Value"
        ] = self.sel_value
        while (
            self.controller.speedgoat.params["Motors/selectPseudoMotor/Value"]
            != self.sel_value
        ):
            gevent.sleep(0.00001)  # 10us

    def start_move(self):
        self.set_param("moveTrigger/Value", 0)
        self.set_param("moveTrigger/Value", 1)
        self.set_param("moveTrigger/Value", 0)

    def stop(self):
        self.set_param("stoppTrigger/Value", 0)
        self.set_param("stoppTrigger/Value", 1)
        self.set_param("stoppTrigger/Value", 0)

    def limits(self):
        lim_pos = self.get_param("motorLimit/UpperLimit")
        lim_neg = self.get_param("motorLimit/LowerLimit")

        return (lim_neg, lim_pos)


##########################################################################
##########                                                      ##########
##########                     Speedgoat Scopes                 ##########
##########                                                      ##########
##########################################################################


class Scope(object):
    def __init__(self, speedgoat, scope_id):
        self.speedgoat = weakref.proxy(speedgoat)
        self.scope_id = scope_id

    @property
    def auto_restart(self):
        return self.speedgoat.sc_get_auto_restart(self.scope_id)

    @auto_restart.setter
    def auto_restart(self, auto_restart):
        self.speedgoat.sc_set_auto_restart(self.scope_id, auto_restart)

    @property
    def decimation(self):
        return self.speedgoat.sc_get_decimation(self.scope_id)

    @decimation.setter
    def decimation(self, decimation):
        self.speedgoat.sc_set_decimation(self.scope_id, decimation)

    @property
    def num_samples(self):
        # print("GET num_samples", end=" ... ")
        return self.speedgoat.sc_get_num_samples(self.scope_id)
        # print("Done")

    @num_samples.setter
    def num_samples(self, num_samples):
        # print("SET num_samples", end=" ... ")
        self.speedgoat.sc_set_num_samples(self.scope_id, num_samples)
        # print("Done")

    @property
    def trigger_level(self):
        return self.speedgoat.sc_get_trigger_level(self.scope_id)

    @trigger_level.setter
    def trigger_level(self, trigger_level):
        self.speedgoat.sc_set_trigger_level(self.scope_id, trigger_level)

    @property
    def trigger_mode(self):
        return self.speedgoat.sc_get_trigger_mode(self.scope_id)

    @trigger_mode.setter
    def trigger_mode(self, trigger_mode):
        self.speedgoat.sc_set_trigger_mode(self.scope_id, trigger_mode)

    @property
    def trigger_scope(self):
        return self.speedgoat.sc_get_trigger_scope(self.scope_id)

    @trigger_scope.setter
    def trigger_scope(self, trigger_scope):
        self.speedgoat.sc_set_trigger_scope(self.scope_id, trigger_scope)

    @property
    def trigger_scope_sample(self):
        return self.speedgoat.sc_get_trigger_scope_sample(self.scope_id)

    @trigger_scope_sample.setter
    def trigger_scope_sample(self, trigger_scope_sample):
        self.speedgoat.sc_set_trigger_scope_sample(self.scope_id, trigger_scope_sample)

    @property
    def trigger_signal(self):
        return self.speedgoat.sc_get_trigger_signal(self.scope_id)

    @trigger_signal.setter
    def trigger_signal(self, trigger_signal):
        self.speedgoat.sc_set_trigger_signal(self.scope_id, trigger_signal)

    @property
    def trigger_slope(self):
        return TriggerSlope(self.speedgoat.sc_get_trigger_slope(self.scope_id))

    @trigger_slope.setter
    def trigger_slope(self, trigger_slope):
        self.speedgoat.sc_set_trigger_slope(self.scope_id, trigger_slope)

    @property
    def num_pre_post_samples(self):
        return self.speedgoat.sc_get_num_pre_post_samples(self.scope_id)

    @num_pre_post_samples.setter
    def num_pre_post_samples(self, num_pre_post_samples):
        self.speedgoat.sc_set_num_pre_post_samples(self.scope_id, num_pre_post_samples)

    @property
    def state(self):
        return self.speedgoat.sc_get_state(self.scope_id)

    @property
    def type(self):
        return self.speedgoat.sc_get_type(self.scope_id)

    @property
    def signal_list(self):
        # apparently sc_get_signal_list is equivalent to sc_get_signals
        # print("sc_get_signals", end=" ... ")
        ret = self.speedgoat.sc_get_signals(self.scope_id)
        # print("Done")

        return ret

    @property
    def is_finished(self):
        return self.speedgoat.is_sc_finished(self.scope_id)

    def add_signal(self, signal_id):
        self.speedgoat.sc_add_signal(self.scope_id, signal_id)

    def remove_signal(self, signal_id):
        self.speedgoat.sc_rem_signal(self.scope_id, signal_id)

    def start(self):
        self.speedgoat.sc_start(self.scope_id)

    def stop(self):
        self.speedgoat.sc_stop(self.scope_id)

    def software_trigger(self):
        self.speedgoat.sc_software_trigger(self.scope_id)

    def get_data(self, signal_id, first_point=0, num_samples=None, decimation=1):
        if num_samples is None:
            num_samples = self.num_samples
        return self.speedgoat.sc_get_data(
            self.scope_id, signal_id, first_point, num_samples, decimation
        )


class TargetScope(Scope):
    @property
    def grid(self):
        return self.speedgoat.tg_sc_get_grid(self.scope_id)

    @grid.setter
    def grid(self, grid):
        self.speedgoat.tg_sc_set_grid(self.scope_id, grid)

    @property
    def mode(self):
        return ScopeMode(self.speedgoat.tg_sc_get_mode(self.scope_id))

    @mode.setter
    def mode(self, mode):
        self.speedgoat.tg_sc_set_mode(self.scope_id, mode)


##########################################################################
##########                                                      ##########
##########             Speedgoat Parameters / Signals           ##########
##########                                                      ##########
##########################################################################


class Parameters(object):
    def __init__(self, speedgoat):
        self.speedgoat = weakref.proxy(speedgoat)

    def __getitem__(self, name):
        if isinstance(name, str):
            block, name = name.rsplit("/", 1) if "/" in name else ("", name)
            return self.speedgoat.get_param_value_from_name(block, name)
        block_names = [bn.rsplit("/", 1) if "/" in bn else ("", bn) for bn in name]
        return self.speedgoat.get_param_value_from_names(*block_names)

    def __setitem__(self, name, value):
        if isinstance(name, str):
            block, name = name.rsplit("/", 1)
            self.speedgoat.set_param_value_from_name(block, name, value)
            return
        # TODO: set multiple items
        raise NotImplementedError

    def keys(self):
        result = []
        param_dict = self.speedgoat.load()["param_dict"]
        for block_name, data in param_dict.items():
            for key in data:
                result.append(block_name + "/" + key)
        return result


class Signals(object):
    def __init__(self, speedgoat):
        self.speedgoat = weakref.proxy(speedgoat)

    def __getitem__(self, name):
        if isinstance(name, str):
            tree = self.speedgoat._cache["signal_tree"]
            node = tree.get_node(name)
            idx = node.data["idx"]
            return self.speedgoat.get_signal_value_from_idxs([idx])[0]
            # block, name = name.rsplit("/", 1) if "/" in name else ("", name)
            # return self.speedgoat.get_signal_value_from_name(block, name)
        # block_names = [bn.rsplit("/", 1) if "/" in bn else ("", bn) for bn in name]
        # return self.speedgoat.get_signal_value_from_names(*block_names)


##########################################################################
##########                                                      ##########
##########                    Speedgoat Object                  ##########
##########                                                      ##########
##########################################################################


class Speedgoat(object):
    def __init__(self, name, config):
        url = _to_zerorpc_url(config["url"], default_port=8200)
        self._log = logging.getLogger("{}({})".format(type(self).__name__, name))
        self._conn = rpc.Client(url)
        self._cache = dict(
            params=None,
            param_dict=None,
            param_tree=None,
            signals=None,
            signal_dict=None,
            signal_tree=None,
            motors=None,
            scopes=None,
            counters=None,
        )
        self.params = Parameters(self)
        self.signals = Signals(self)
        self.name = name
        self.regul = Regul(self)

        self.load()

    def set_fix_exit(self, value):
        self.params["setPoint/beam_offset(mm)/Value"] = value
        while self.params["setPoint/beam_offset(mm)/Value"] != value:
            gevent.sleep(0.00001)  # 10us

    @property
    def app_name(self):
        return self._conn.get_app_name()

    @property
    def is_app_running(self):
        return self._conn.is_app_running()

    @property
    def is_overloaded(self):
        return self._conn.is_overloaded()

    @property
    def sample_time(self):
        return self._conn.get_sample_time()

    @sample_time.setter
    def sample_time(self, sample_time):
        self._conn.set_sample_time(sample_time)

    @property
    def signal_tree(self):
        return self.load()["signal_tree"]

    def get_signal_index(self, name):
        tree = self.signal_tree
        node = tree.get_node(name)
        return node.data["idx"]

    @property
    def counters(self):
        return self.load()["counters"]

    @property
    def counters_controller(self):
        return self.load()["counters_controller"]

    @property
    def motors(self):
        return self.load()["motors"]

    @property
    def motors_controller(self):
        return self.load()["motors_controller"]

    @property
    def scopes(self):
        return self.load()["scopes"]

    @property
    def param_tree(self):
        return self.load()["param_tree"]

    # @print_trace
    def load(self, force=False):
        """Reload cache (parameter, signals, counters, motors and scope information)"""

        # Parameters
        params = self._cache["params"]
        if params is None or force:
            self._cache["params"] = params = self.get_param_infos()
            self._cache["param_dict"] = create_block_dict(params)
            self._cache["param_tree"] = create_tree(params)

        # Signals
        signals = self._cache["signals"]
        if signals is None or force:
            self._cache["signals"] = signals = self.get_signal_infos()
            self._cache["signal_dict"] = create_block_dict(signals)
            self._cache["signal_tree"] = create_tree(signals)

        # Socpes
        scopes = self._cache["scopes"]
        if scopes is None or force:
            self._cache["scopes"] = scopes = {}
            for scope_id in self.get_scope_list():
                scope_type = self.sc_get_type(scope_id)
                if scope_type == ScopeType.Target:
                    scope = TargetScope(self, scope_id)
                else:
                    scope = Scope(self, scope_id)
                scopes[scope_id] = scope

        # Motors
        motors = self._cache["motors"]
        if motors is None or force:
            self._cache["motors_controller"] = None
            # register Speedgoat signal for motors controller
            tree = self._cache["signal_tree"]
            signal_node = list(
                tree.filter_nodes(functools.partial(is_motors_controller_node, tree))
            )
            # register Speedgoat params for motors controller
            tree = self._cache["param_tree"]
            param_node = list(
                tree.filter_nodes(functools.partial(is_motors_controller_node, tree))
            )
            if (len(signal_node) == 1) and (len(param_node) == 1):
                self._cache["motors_controller"] = ctrl = MotorsController(
                    self, signal_node[0], param_node[0]
                )
                self._cache["motors"] = ctrl.available_motors

        # Counters
        counters = self._cache["counters"]
        if counters is None or force:
            self._cache["counters_controller"] = None
            # register Speedgoat signals for counters
            tree = self._cache["signal_tree"]
            signal_node = list(
                tree.filter_nodes(functools.partial(is_counters_controller_node, tree))
            )
            # register Speedgoat params for counters
            tree = self._cache["param_tree"]
            param_node = list(
                tree.filter_nodes(functools.partial(is_counters_controller_node, tree))
            )
            if (len(signal_node) == 1) and (len(param_node) == 1):
                self._cache["counters_controller"] = ctrl = SpeedgoatCountersController(
                    self, signal_node[0], param_node[0]
                )
                self._cache["counters"] = ctrl.counters

        return self._cache

    def get_daq(self):
        return DAQ(self, self.scopes[11])

    def get_fastdaq(self):
        return FastDAQ(self, self.scopes[10])

    def get_daqs(self):
        pi = self.get_param_infos()
        tree = create_tree(pi)
        ring_buffers = tree.filter_nodes(functools.partial(is_ring_buffer_node, tree))
        return ring_buffers

    def sc_get_type(self, scope_id):
        return ScopeType(self._conn.sc_get_type(scope_id))

    def sc_get_state(self, scope_id):
        return ScopeState(self._conn.sc_get_state(scope_id))

    def sc_get_trigger_mode(self, scope_id):
        return TriggerMode(self._conn.sc_get_trigger_mode(scope_id))

    def sc_get_trigger_slope(self, scope_id):
        return TriggerSlope(self._conn.sc_get_trigger_slope(scope_id))

    def tg_sc_get_mode(self, scope_id):
        return ScopeMode(self._conn.tg_sc_get_mode(scope_id))

    def __getattr__(self, name):
        server_call = getattr(self._conn, name)

        def func(*args):
            return server_call(*args)

        func.__name__ = name
        setattr(self, name, func)
        return func

    def set_param(self, param, value):
        self.params[param] = value
        ret_val = self.params[param]
        while self.get_param(param) != value:
            gevent.sleep(0.00001)  # 10us

    def get_param(self, param):
        return self.params[param]

    def get_signal(self, signal):
        return self.signals[signal]
