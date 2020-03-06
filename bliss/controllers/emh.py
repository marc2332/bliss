# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ESRF - ALBA EMH electrometer

Example YAML_ configuration:

.. code-block:: yaml

    plugin: bliss
    class: EMH
    name: emeter2
    tcp:
      url: emeter2.esrf.fr
    counters:
    - counter_name: e1
      channel: 1
    - counter_name: e2
      channel: 2

Usage::

    >>> from bliss.config.static import get_config
    >>> from bliss.controllers.EMH import ...
    >>> config = get_config()

    >>> em.test_hw()

"""

import re
import time
import numpy as np

from bliss.comm.util import get_comm, TCP

from bliss import global_map
from bliss.common.logtools import *

from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import CounterController

from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave

TRIGGER_INPUTS = {"DIO_1", "DIO_2", "DIO_3", "DIO_4"}
TRIGGER_MODES = ("SOFTWARE", "HARDWARE", "AUTOTRIGGER")
TRIGGER_POLARITIES = ("RISING", "FALLING")
ACQUISITION_MODES = ("INTEGRATION", "CHARGE")
ACQU_FILTER_SPEEDS = (3200, 100, 10, 1, 0.5)
RANGE_STRINGS = ("100pA", "1nA", "10nA", "100nA", "1uA", "10uA", "100uA", "1mA", "AUTO")
ACQUISITION_STATES = (
    "STATE_INIT",
    "STATE_ON",
    "STATE_ACQUIRING",
    "STATE_FAULT",
    "STATE_RUNNING",
)


class EmhCounter(SamplingCounter):
    """EMH counter class
    """

    def __init__(self, name, channel, controller, unit=None):

        SamplingCounter.__init__(self, name, controller)
        #                                    ref to the controller
        # the reading of many counters depending on the same
        # controller will be performed using  controller.read_all() function

        self.channel = channel

    def __info__(self):
        info_str = "info string from counter"
        info_str += f"chan={self.channel}"
        return info_str


class EMH(CounterController):
    """ EMH controller
    """

    def __init__(self, name, config):
        super().__init__(name)

        # self.name = name
        self.bliss_config = config

        self.comm = get_comm(config, TCP, eol="\r\n", port=5025)

        # Logging and debug
        global_map.register(self, children_list=[self.comm], tag=self.name)

        # BPM COUNTERS
        for counter_conf in config.get("counters", list()):
            unit = counter_conf.get_inherited("unit")
            self.create_counter(
                EmhCounter,
                counter_conf["counter_name"],
                counter_conf["channel"],
                unit=unit,
            )

        self.bpm_values = {"bpmx": -1, "bpmy": -1, "bpmi": -1}

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):

        trigger_type = acq_params.pop("trigger_type")

        if trigger_type == "HARDWARE":
            from bliss.scanning.acquisition.emh import EmhAcquisitionSlave

            return EmhAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)
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

        trigger_type = acq_params.get("trigger_type", "AUTOTRIGGER")

        params = {
            "count_time": count_time,
            "npoints": npoints,
            "trigger_type": trigger_type,
        }
        return params

    def read_all(self, *counters):
        """Read all channel of the EMH controller and perform BPM calculations.
        """
        curr_list = self.get_currents()
        vlist = list()

        # BPM calculation.
        #    _________
        #   |_c1_|_c2_|   ↑
        #   | c4 | c3 |   y  x→
        #    ---------
        c1, c2, c3, c4 = self.get_currents()
        csum = c1 + c2 + c3 + c4
        if csum != 0:
            bpm_x = ((c1 + c4) - (c2 + c3)) / csum
            bpm_y = ((c1 + c2) - (c3 + c4)) / csum
        else:
            bpm_x = 0
            bpm_y = 0

        self.bpm_values["bpmi"] = csum
        self.bpm_values["bpmx"] = bpm_x
        self.bpm_values["bpmy"] = bpm_y

        log_info(self, "BPM values: I=%s X=%s Y=%s", csum, bpm_x, bpm_y)

        # Counters filling.
        for counter in counters:
            # ???
            if type(counter.channel) == type(1):
                vlist.append(curr_list[counter.channel - 1])
            else:
                vlist.append(self.bpm_values[counter.channel])

        return vlist

    def raw_write(self, message):
        """Send <message> to the controller.
        * type of <message> must be 'str'
        * converts <message> into 'bytes'
        * no terminator char ???
        * send command to the device
        * NO answer is read from controller
        """
        self.comm.write(message.encode())

    def raw_write_read(self, message):
        """Send <message> to the controller and read the answer.
        * type of <message> must be 'str'
        * converts <message> into 'bytes'
        * no terminator char ???
        * send command to the device
        * return answer from controller as a 'str' string
        """
        ans = self.comm.write_readline(message.encode()).decode()
        return ans

    def get_id(self):
        """Return identification string.
        Return value is like: 'ALBASYNCHROTRON,Electrometer2,000000007, 1.0.00'
        """
        return self.raw_write_read("*IDN?")

    def get_mac_address(self):
        """Return a string representing the MAC address of the device.
        """
        return self.raw_write_read("*MAC?")

    def get_fw_version(self):
        """Return firmware version
        Return value is a string like: ???
        """
        return self.raw_write_read("FWVE?")

    def get_fw_date(self):
        """Return firmware date
        Return value is a string like: ???
        """
        return self.raw_write_read("FWDA?")

    def reboot(self):
        """Send Reboot command to EMH device.
        """
        self.raw_write("*RST")

    def get_info(self):
        """Return list of string info taken from controller.
        """
        list_info = list()
        list_info.append(self.get_id())
        list_info.append(self.get_mac_address())
        list_info.append(self.get_fw_version())
        list_info.append(self.get_temperature_cb())
        list_info.append(self.get_temperature_fe())
        list_info.append(self.get_supplies_voltages())
        return list_info

    def __info__(self):
        """Return info string used by BLISS shell.
        """
        info_string = "EMH controller info:\n"
        info_string += "\n".join(self.get_info())
        return info_string

    def get_chan_info(self, chan):
        """Return info string of channel <chan>.
        """
        chan_info_string = f"CH{chan}::saturation max:{self.get_saturation_max(chan)}"
        return chan_info_string

    def get_temperature_cb(self):
        """ Return temperature of carrier board"""
        return self.raw_write_read("DIAG:CBTE?")

    def get_temperature_fe(self):
        """ Return temperature of froint-end board"""
        return self.raw_write_read("DIAG:FETE?")

    def get_supplies_voltages(self):
        """
        Return voltages sent to voltages supplies.
        """
        return self.raw_write_read("DIAG:VSEN?")

    """ TRIGGER """

    def get_trigger_delay(self):
        """
        Return delay after trigger.
        Return value is an integer in milliseconds.
        """
        return int(self.raw_write_read("TRIG:DELA?"))

    def get_trigger_input(self):
        """
        Return input used for the trigger.
        Return value is a string like 'DIO_1'.
        """
        return self.raw_write_read("TRIG:INPU?")

    def set_trigger_input(self, trigger_input):
        """
        Set trigger input to <trigger_input>
        <trigger_input is a string in {'DIO_1', 'DIO_2', 'DIO_3', 'DIO_4'}
        """
        if trigger_input in TRIGGER_INPUTS:
            self.raw_write("TRIG:INPU {}".format(trigger_input))
        else:
            raise ValueError("Bad trigger input : {}".format(trigger_input))

    def get_trigger_mode(self):
        """
        Return trigger mode.
        Return value is a string in {'SOFTWARE', 'HARDWARE', 'AUTOTRIGGER'}
        """
        ans = self.raw_write_read("TRIG:MODE?")
        if ans in TRIGGER_MODES:
            return ans
        else:
            raise RuntimeError("Bad trigger mode received from EMH: {}".format(ans))

    def set_trigger_mode(self, trigger_mode):
        """
        Set trigger mode to <trigger_mode>.
        <trigger_mode> must be a string in {'SOFTWARE', 'HARDWARE', 'AUTOTRIGGER'}
        """
        if trigger_mode in TRIGGER_MODES:
            self.raw_write("TRIG:MODE {}".format(trigger_mode))
        else:
            raise ValueError("Bad trigger mode : {}".format(trigger_mode))

    def get_trigger_polarity(self):
        """
        Return Trigger polarity.
        Return value is a string in (FALLING, RISING)
        """
        return self.raw_write_read("TRIG:POLA?")

    def set_trigger_polarity(self, pola):
        """
        Set Trigger polarity.
        <pola> is a string in ('RISING', 'FALLING').
        """
        if pola in TRIGGER_POLARITIES:
            self.raw_write("TRIG:POLA {}".format(pola))
        else:
            raise ValueError("invalid polarity: {}".format(pola))

    def get_trigger_state(self):
        """
        Return trigger configuration as a string like :
        '[['MODE', 'SOFTWARE'], ['POLARITY', 'RISING'],
        ['DELAY', 0], ['INPUT', 'DIO_1']]'
        """
        return self.raw_write_read("TRIG:STATE?")

    def get_acq_filter_speed(self):
        """
        Return acquisition filter speed configuration in Hz.
        Return value is a float in {3200; 100; 10; 1; 0.5}.
        """
        ans = float(self.raw_write_read("ACQU:FILT?")[:-2])

        if ans in ACQU_FILTER_SPEEDS:
            return ans

        raise ValueError("Invalid speed value: {}".format(ans))

    def set_acq_filter_speed(self, speed):
        """
        Set acquisition filter speed to <speed>.
        <speed> must be is a float in {3200; 100; 10; 1; 0.5}.
        """
        if speed in ACQU_FILTER_SPEEDS:
            self.raw_write("ACQU:FILT {}".format(speed))
        else:
            raise ValueError("Invalid speed value: {}".format(speed))

    def get_acq_mode(self):
        """
        Return a string in {'INTEGRATION'; 'CHARGE'}
        representing the acquisition mode in use.
        """
        return self.raw_write_read("ACQU:MODE?")

    def set_acq_mode(self, mode):
        """
        Set <mode> as acquisition mode.
        <mode> must be a string in {'INTEGRATION'; 'CHARGE'}
        """
        if mode in ACQUISITION_MODES:
            self.raw_write("ACQU:MODE {}".format(mode))
        else:
            raise ValueError("{} is not a valid acquisition mode".format(mode))

    def get_acq_measures(self, start=None, count=1):
        """
        Return the raw current buffer of last acquisitions.

        If <start> is defined, it returns <count> events starting at event <start>.

        Return value is a string like:
        [['CHAN01', [[1.3517003600000002, 8.841504037466135e-05], [1.6896203600000002,
        8.8979398731919311e-05]]], ['CHAN02', [[1.3517003600000002, 9.9560896073699361e-05],
        [1.6896203600000002, 9.9569267980199373e-05]]], ['CHAN03', [[1.3517003600000002,
        6.6801692519604324e-05], [1.6896203600000002, 6.751058191963094e-05]]], ['CHAN04',
        [[1.3517003600000002, 7.8305705642127727e-05], [1.6896203600000002,
        7.8270846516267247e-05]]]]

        """
        if start is None:
            return self.raw_write_read("ACQU:MEAS?")
        else:
            return self.raw_write_read("ACQU:MEAS? {},{}".format(start, count))

    def get_acq_data(self, start=None, count=1):
        """
        Return lists of timestamps and parsed data.
        """

        raw_data = self.get_acq_measures(start, count)
        chan_data = raw_data[1:-1].split("['CHAN")[1:]

        # we suppose that all the channels have been read
        # in current and timestamps, the channel index are:
        # 0:C1 1:C2 2:C3 3:C4 4:bpmx 5:bpmy 6:bpmi
        currents = np.zeros((7, count))
        timestamps = np.zeros((7, count))
        match_number = re.compile(r"-?\ *[0-9]+\.?[0-9]*(?:[Ee]\ *-?\ *[0-9]+)?")

        for chan in range(4):
            chan_rdata = chan_data[chan].strip()
            numbers = match_number.findall(chan_rdata)
            channel = int(numbers[0])  # channel number
            data = numbers[1:]  # [timestamp + current]
            currents[chan] = data[1::2]
            timestamps[chan] = data[0::2]

        for pt_index in range(count):
            csum = (
                currents[0][pt_index]
                + currents[1][pt_index]
                + currents[2][pt_index]
                + currents[3][pt_index]
            )
            currents[6][pt_index] = csum
            currents[4][pt_index] = (
                (currents[0][pt_index] + currents[3][pt_index])
                - (currents[1][pt_index] + currents[2][pt_index])
            ) / csum
            currents[5][pt_index] = (
                (currents[0][pt_index] + currents[1][pt_index])
                - (currents[2][pt_index] + currents[3][pt_index])
            ) / csum

        return (timestamps, currents)

    def get_acq_counts(self):
        """
        Return number of events detected.
        Return value is an integer.
        """
        ans = int(self.raw_write_read("ACQU:NDAT?"))
        return ans

    def get_acq_range(self):
        """
        Return acquisition range as a string in
        {100pA, 1nA, 10nA, 100nA, 1uA, 10uA, 100uA, 1mA}
        """
        return self.raw_write_read("ACQU:RANGE?")

    def set_acq_range(self, str_range):
        """
        Set acquisition range to <str_range>.
        <str_range> must be a string in {100pA, 1nA, 10nA,
        100nA, 1uA, 10uA, 100uA, 1mA, AUTO}
        """
        if str_range in RANGE_STRINGS:
            self.raw_write("ACQU:RANGE {}".format(str_range))
            # ??? can be long ??? sleep needed ?

            # to check : what happens if talk during setting ?

            time.sleep(5)
        else:
            raise ValueError("invalid acquisition range: {}".format(str_range))

    def set_acq_range_pA(self, pArange):
        """
        Set acquisition range to <pArange> pA.
        <pArange> value should be an integer in range [100; 1e9].
        <pArange> unit is pA.
        """
        if pArange < 100 or pArange > 1e9:
            raise ValueError("invalid pA acquisition range: {}".format(pArange))

        if pArange == 100:
            value = 100
            unit = "pA"
        elif pArange in [1e3, 1e4, 1e5]:
            value = int(pArange / 1e3)
            unit = "nA"
        elif pArange in [1e6, 1e7, 1e8]:
            value = int(pArange / 1e6)
            unit = "uA"
        elif pArange == 1e9:
            value = int(pArange / 1e9)
            unit = "mA"
        else:
            raise ValueError("invalid range:{}".format(pArange))

        range_string = "{}{}".format(value, unit)
        self.set_acq_range(range_string)

    def get_acq_trig(self):
        """Return number of points to acquire (NTRIG?).
        Return value is an integer.
        """
        return int(self.raw_write_read("ACQU:NTRI?"))

    def set_acq_trig(self, trigger_count):
        """Set number of points to acquire (NTRIG command).
        <trigger_count> must be an integer.
        0 value means infinite number of points to acquire.
        """
        self.raw_write("ACQU:NTRI {}".format(trigger_count))

    def get_acq_status(self):
        """
        Return acquisition status.
        Return value is a string like : 'Equipment ready'.
        """
        ans = self.raw_write_read("ACQU:STUS?")
        return ans

    def get_acq_state(self):
        """
        Return acquisition state.
        Return value is a string in {'STATE_INIT', 'STATE_ON', 'STATE_ACQUIRING', 'STATE_FAULT'}
        """
        ans = self.raw_write_read("ACQU:STAT?")
        if ans in ACQUISITION_STATES:
            return ans

        raise RuntimeError("EMH returned an invalid state : {}".format(ans))

    def get_acq_time(self):
        """
        Return acquisition time in milliseconds.
        Return value is an integer in range [;].
        """
        return int(self.raw_write_read("ACQU:TIME?"))

    def set_acq_time(self, acq_time):
        """
        Set acquisition time in milliseconds.
        <acq_time> must be an integer in range [;].
        """
        self.raw_write("ACQU:TIME {}".format(acq_time))

    def print_acq_info(self):
        """
        Return many info about acquisition configuration.
        """
        print("Acquisition status   : {}".format(self.get_acq_status()))
        print("Acquisition mode     : {}".format(self.get_acq_mode()))
        print("Acquisition counts   : {}".format(self.get_acq_counts()))
        print("Acquisition filter   : {}".format(self.get_acq_filter_speed()))
        print("Acquisition range    : {}".format(self.get_acq_range()))
        print("Acquisition state    : {}".format(self.get_acq_state()))
        print("Acquisition time     : {} ms".format(self.get_acq_time()))
        print("Acquisition triggers : {}".format(self.get_acq_trig()))
        print()
        print("Trigger delay        : {}".format(self.get_trigger_delay()))
        print("Trigger input        : {}".format(self.get_trigger_input()))
        print("Trigger mode         : {}".format(self.get_trigger_mode()))
        print("Trigger polarity     : {}".format(self.get_trigger_polarity()))

    def start_acq(self):
        """Start acquisition but do not send trigger
        """
        self.raw_write("ACQU:START")

    def start_acq_and_run(self):
        """Start acquisition and send a trigger if trigger mode is SOFTWARE.
        """
        self.raw_write("ACQU:START SWTRIG")

    def stop_acq(self):
        """ Stop an acquisition.
        """
        self.raw_write("ACQU:STOP")

    def get_saturation_max(self, chan):
        """ Return saturation max. This parameter defines the maximum
        limit to automatically change the range to a higher value.
        Return value is a float in 0 / 100 %
        """
        raw_data = self.raw_write_read("CHAN0{}:CABO:SMAX?".format(chan))
        data = float(raw_data)
        return data

    def get_saturation_min(self, chan):
        """
        Return saturation min. This parameter defines the minimum
        limit to automatically change the range to a lower value.
        Return value is a float in 0 / 100 %
        """
        raw_data = self.raw_write_read("CHAN0{}:CABO:SMIN?".format(chan))
        data = float(raw_data)
        return data

    def get_voltage_buffer(self, chan, start=None, count=1):
        """
        Return the buffer of voltage measures for channnel <chan> acquiered
        during last run.
        <chan> in {1, 2, 3, 4}
        Return value is a tuple of lists of floats.
        First list is the list of timestamps.
        Second one is the list of voltages.
        """
        if start is None:
            raw_data = self.raw_write_read("CHAN0{}:VOLT?".format(chan))
        else:
            raw_data = self.raw_write_read(
                "CHAN0{}:VOLT? {},{}".format(chan, start, count)
            )

        data = raw_data.replace("[", "").replace("]", "").replace(",", "").split()
        timestamps = [float(x) for x in data[0::2]]
        voltages = [float(x) for x in data[1::2]]
        return (timestamps, voltages)

    """ CURRENTS """

    def get_current_buffer(self, chan, start=None, count=1):
        """
        Return the buffer of current measures for channnel <chan> acquiered
        during last run.
        <chan> in {1, 2, 3, 4}
        Return value is a tuple of lists of floats.
        First list is the list of timestamps.
        Second one is the list of currents.
        """
        if start is None:
            raw_data = self.raw_write_read("CHAN0{}:CURR?".format(chan))
        else:
            raw_data = self.raw_write_read(
                "CHAN0{}:CURR? {},{}".format(chan, start, count)
            )
        data = raw_data.replace("[", "").replace("]", "").replace(",", "").split()
        timestamps = [float(x) for x in data[0::2]]
        currents = [float(x) for x in data[1::2]]
        return (timestamps, currents)

    def get_current(self, chan):
        """
        Return instant current measured on channel <chan>.
        <chan> must be an integer in {1, 2, 3, 4}.
        Return value is a float.
        """
        _ans = self.raw_write_read("CHAN0{}:INSC?".format(chan))
        _curr = float(_ans)
        return _curr

    def get_currents(self):
        """
        Return a list of floats representing instant currents
        measured on the 4 channels.
        """
        raw_data = self.raw_write_read(
            "CHAN01:INSC?;CHAN02:INSC?;CHAN03:INSC?;CHAN04:INSC?"
        )
        # raw_data is a string like :
        # '9.07923344075e-05;0.000100710227393;6.5532028605e-05;7.59496542586e-05'
        currents = [float(x) for x in raw_data.split(";")]
        return currents

    """ SEQUENCES """

    def pulse(self):
        """Send a command to EMH controller to make a pulse signal
        """
        self.raw_write("TRIG:SWSE True")

    def make_N_acq(self, acq_count, acq_time):
        """
        Performs <acq_count> acquisitions of <acq_time> ms.
        """

        if self.get_acq_state() != "STATE_ON":
            # print("stop acquisition")
            self.stop_acq()
            time.sleep(0.1)

        start_nb_pulse = self.get_acq_counts()
        last_acq = 0
        self.set_acq_trig(acq_count + 1)
        em_wait()
        # print("acq trig set")

        self.set_acq_time(acq_time)  # ms
        em_wait()
        # print("acq time set")

        self.set_trigger_mode("SOFTWARE")
        em_wait()
        # print("trig mode set")

        self.start_acq()
        # print("acq started")
        time.sleep(0.1)

        ss = self.get_acq_state()

        while ss != "STATE_ON":
            nb_data_generated = self.get_acq_counts()

            ss = self.get_acq_state()
            # print(
            #    " nb point: %d (%d/%d) STATE: %s"
            #    % (nb_data_generated, start_nb_pulse, acq_count, ss)
            # )

        # print(
        #    " pulses received: %d (%d/%d) STATE: %s"
        #    % (nb_data_generated, start_nb_pulse, acq_count, ss)
        # )

    def test_hw(self):
        print(self.raw_write_read("*IDN?"))
        print(self.get_id())
        print(self.get_mac_address())
        print(self.get_fw_version())
        print(self.get_fw_date())
        print(self.get_chan_info(1))
        print(self.get_chan_info(2))
        print(self.get_chan_info(3))
        print(self.get_chan_info(4))
        print(self.get_temperature_cb())
        print(self.get_temperature_fe())
        print(self.get_supplies_voltages())
        print(self.get_trigger_delay())
        print(self.get_trigger_input())
        print(self.get_trigger_mode())
        print(self.get_trigger_polarity())
        print(self.get_trigger_state())
        print(self.get_acq_filter_speed())
        print(self.get_acq_mode())


def em_wait():
    time.sleep(0.2)


"""
emeter2.stop_acq()
emeter2.set_acq_trig(13)
emeter2.set_acq_time(334)
emeter2.set_trigger_mode('AUTOTRIGGER')
emeter2.start_acq()
time.sleep(2)
print emeter2.get_acq_state()

print emeter2.get_acq_state()



"""
