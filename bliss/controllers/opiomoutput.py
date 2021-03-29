# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Generate output pulses with the OPIOM, using the Default Progtam.
Generate a single pulse or use the Time Patern Generator (TPG) mode to
generate a predefined time pattern using up to eight outputs simultaneously.
Only one counter can be configured as TPG.

yml configuration example:
class: OpiomOutput
name: ttl
opiom: $laser_opiom
default_acq_params_file: /users/opid29s/local/acq_parameters/acq.params
outputs:
    -
     type: TPG
     channel: 1
    -
     alias: laser1
     channel: 1
    -
     alias: laser2
     channel: 2
    ...

Acquisition parameters file example:
#period: 1000
#channel_nb     delay   width   polarity
1               0       200     Normal
2               100     200     Normal
3               200     50      Normal
4               400     10      Normal
5               600     50      Inversed
"""

from bliss.common import log
from bliss.common.cleanup import error_cleanup


class OpiomOutput:
    """Communicate with the OPIOM. Calculate output sequences"""

    def __init__(self, name, config):
        self.opiom = config.get("opiom")
        self.channels = config["outputs"]
        self._channels_mask = 0
        for chan in self.channels:
            try:
                if chan["type"] == "TPG":
                    self.tpg_channel = chan["channel"]
            except KeyError:
                self._channels_mask += 1 << (chan["channel"] - 1)
        self.default_acq_params_file = config.get("default_acq_params_file")
        self.acq_params_dict = {}
        self.acq_params_file = None
        self.acq_period = None
        self.nb_repetition = None

    def _oo_reset(self):
        """Reset output to GND level. Reset all the channels.
        """
        # reset the TPG channel, if any
        if self.tpg_channel:
            self.opiom.comm("CNT %d RESET" % self.tpg_channel)

        # reset the channels level to GND
        for chan in self.channels:
            self._oo_level(chan["channel"], 0)

        # reset ouptut to ground in case some inversed polarities were used
        self.opiom.comm("IMA 0x00")

    def _oo_level(self, channel, level=0):
        """Set the level of a non TPG channel
        Args:
            channel (int): Channel number (1-8)
        Kwargs:
            level (int): 0 (GND) or 1 (TTL). Default value is 0
        """
        self.opiom.comm("SPBIT %1d %1d" % (channel, level))

    def _oo_state(self, channel):
        """Read the channel status
        Args:
            channel (int): Channel number (1-8)
        Returns:
            status (str):  DISABLED, RUN, STOP
        """
        answ = self.opiom.comm("?SCNT %d" % channel)
        return answ

    def _oo_chan_read(self, channel):
        """Read the channel value
        Args:
            channel (int): Channel number to read (1-8)
        Returns:
            value (int): The value of the specified channel
        Raises:
            RuntimeError: Cannot read the value from the channel
        """
        try:
            return int(self.opiom.comm("?VCNT %d" % channel), 16)
        except ValueError:
            msg = "channel %d" % channel
            for chan in self.channels:
                if chan["channel"] == channel:
                    msg = "%s" % chan["alias"]
            raise RuntimeError("Cannot read the value for %s" % msg)

    def _oo_polarity_set(self, value=False):
        """Set the bit mask of the output polarities
        Args:
            value (int): Bitmask value
        """
        log.debug("output polarity set to %s " % ("inversed" if value else "normal"))
        self.opiom.comm("IMA 0x%02x" % value)

    def _oo_tpg_clear(self):
        """Clear the TPG table
        """
        self.opiom.comm("TPG CLEAR")

    def _oo_tpg_add(self, duration, mask):
        """Add a line at the end of the TPG table.
        Args:
            duration (int): duration of the pulse [ms]
            mask (int): the value of the unmasked bits (a bit is unmasked
                        if set to 1.
        """
        log.debug("Add patern for %d ms, output mask %02x" % (duration, mask))
        self.opiom.comm("TPG ADD 0x%02x %d" % (mask, duration))

    def _oo_tpg_read(self):
        """Read the content of the TPG table.
        Returns:
            data(list): List of lines, present in the TPG table
        """
        return self.opiom.comm("?TPG")

    def _oo_tpg_set(self, nb_repetition=1):
        """Set an output patern configuration and repetition.
        Args:
            nb_repetion (int): number of pulse-series repetitions
                               (0 = infinite loop)
        """
        log.debug("Set TPG channel, %d repetition(s)" % nb_repetition)

        # Hardcoded selection in order to have pulse duration in ms:
        # internal clock - CLK2 (2MHz = 0.5us) and the period 2000
        # so 2000*0.5us = 1ms
        # 1 0 means execute table from the first(1) to the last line(0)
        # use all the configured channels - self._channels_mask

        self.opiom.comm(
            "CNT %d CLK2 TPG 0x%02x 2000 1 0 LOOP %d"
            % (self.tpg_channel, self._channels_mask, nb_repetition)
        )

    def _oo_pulse_set(self, channel, delay, width, nb_repetition=1):
        """Set a pulse for a given channel. Repeat it if needed.
        Args:
            channel (int): Output channel number (1-8)
            delay (int): Delay from the start [ms]
            width (int): Duration of the pulse [ms]
            nb_repetition (int): Number of repetitions of the pulse
        """
        # Hardcoded selection in order to have pulse duration in ms:
        # internal clock - CLK2 (2MHz = 0.5us) and the period 2000
        # so 2000*0.5us = 1ms

        self.opiom.comm(
            "CNT %d CLK2 PULSE %d %d %d" % (channel, delay, width, nb_repetition)
        )

    def _oo_start(self, channel=None):
        """Start a channel.
        Args:
            channel (int): Channel number (1-8).
                           If None, the TPG channel will be started
        """
        if self.tpg_channel and channel is None:
            log.debug("Start the TPG channel %d" % self.tpg_channel)
            self.opiom.comm("CNT %d START" % self.tpg_channel)
        else:
            log.debug("Start channel %d" % channel)
            self.opiom.comm("CNT %d START" % channel)

    def _oo_stop(self, channel=None):
        """Stop a channel or the TPG channel. Reset the other channels to
           ground level.
        Args:
            channel (int): Channel number (1-8).
                           If None, the TPG channel will be started
        """
        if self.tpg_channel and channel is None:
            self.opiom.comm("CNT %d STOP" % self.tpg_channel)

            # reset the channels level to GND
            for chan in self.channels:
                self._oo_level(chan["channel"], 0)
        else:
            self.opiom.comm("CNT %d STOP" % channel)
            # reset the channel level to GND
            self._oo_level(channel, 0)

    def config_sequence(self, duration, mask, polarity=None):
        """Configure the patern sequence
        Args:
            duration (list): list of pattern durations - integer values [ms]
            mask (list): list of output masks - integer values
        Kwargs:
            polarity (int): output polarity mask
        """
        # clear all paterns
        self._oo_tpg_clear()

        if polarity is not None:
            self._oo_polarity_set(polarity)
        try:
            for numb in range(duration.__len__()):
                self._oo_tpg_add(duration[numb], mask[numb])
            log.info("Added %d paterns" % duration.__len__())
        except (AttributeError, NameError):
            raise RuntimeError("Pattern parameters not set")

    def stop_acquisition(self):
        """Stop the acquisition sequence
        """
        self._oo_stop()

    def start_acquisition(self, nb_repetition=None):
        """Start sequence
        Args:
            nb_repetition (int): Number of repetition of the output pulses
        """
        log.debug("Start sequence")
        if nb_repetition is None:
            nb_repetition = self.nb_repetition
        with error_cleanup(self._oo_stop):
            self._oo_tpg_set(nb_repetition)
            self._oo_start()

    def status(self, verbose=False):
        """Print the execution status of the sequence
        Args:
            verbose (bool): Verbose print
        """
        state = self._oo_state(self.tpg_channel)
        if state == "DISABLED":
            for chan in self.channels:
                self._oo_level(chan["channel"])

        val = self._oo_chan_read(self.tpg_channel)
        if verbose:
            log.info("Channel is %s, channel value = %d" % (state, val))
        return {"state": state, "value": val}

    def _read_params_from_file(self, filename=None):
        """Read the acquisition parameters from a file
        Args:
           filename (str): Filename (full path)
        Returns:
           (tuple): Dictionary with the predefined channels and values.
                    The period [ms]
        """
        values_dict = {}
        if filename is None:
            filename = self.acq_params_file or self.default_acq_params_file
        with open(filename) as fdesc:
            for line in fdesc:
                if line.startswith("#"):
                    try:
                        _, period = line.split(":")
                        period = float(period)
                    except ValueError:
                        labels = list(map(str.lower, line.split()[1:]))
                elif line.strip():
                    value = line.split()
                    values_dict[int(value[0])] = dict(zip(labels, value[1:]))
        return values_dict, period

    def set_acquisition(self, filename=None, period=None, nb_repetition=1):
        """ Get the acquition parameters. Convert them to opiom sequence.
        Write them in the opiom memory
        Args:
            filename (str): filename with the parameters
            period (int): Duration of the while sequence [ms]
            nb_repetition (int): Number of repetition of the sequence
        Raises:
            RuntimeError: Invalid input: duration longer than the period
        """
        self.acq_params_dict, _period = self._read_params_from_file(filename)

        for _key, _val in self.acq_params_dict.items():
            _val.update({"name": self.channels[_key]["alias"]})
            if "enable" not in _val:
                _val.update({"enable": True})

        self.nb_repetition = nb_repetition
        self.acq_period = period or _period

        _times_list = [
            int(k["delay"]) for k in self.acq_params_dict.values() if k["enable"]
        ]
        _times_list = [
            (int(k["delay"]) + int(k["width"]))
            for k in self.acq_params_dict.values()
            if k["enable"]
        ]
        _times_list.append(self.acq_period)
        _times_list = sorted(set(_times_list))

        # check for time overpassing the period.
        if _times_list[-1] > self.acq_period:
            raise RuntimeError("Invalid input: duration longer than the period")

        interval_limits = list(zip(_times_list, _times_list[1:]))
        # print("interval limits", interval_limits)
        duration_list = [(y - x) for x, y in interval_limits]
        # print("duration_list", duration_list)

        output_mask_list = []
        for interval in interval_limits:
            interval_mask = 0
            polarity_mask = 0
            for _key, _val in self.acq_params_dict.items():
                if not _val["enable"]:
                    continue
                else:
                    _min = int(_val["delay"])
                    _max = _min + int(_val["width"])
                    if _min <= interval[0] and _max >= interval[1]:
                        # Laser pulse is inside this interval.
                        # 'bit' for this laser will contribute
                        # to the mask for this this interval.
                        interval_mask |= 1 << (_key - 1)
                    if "Inversed" in _val["polarity"]:
                        polarity_mask |= 1 << (_key - 1)
            output_mask_list.append(interval_mask)
        # print("output_mask_list", output_mask_list)

        self.config_sequence(duration_list, output_mask_list, polarity_mask)
        # print("polarity_mask", polarity_mask)

    def print_acq_parameters(self):
        """ Print the current acquisition parameters
        """
        print("Acquisition parameters:")
        print(" Period [ms]: ", self.acq_period)
        print(" Number of repetitions: ", self.nb_repetition)
        print(" Outputs:")
        for _chan, _params in self.acq_params_dict.items():
            mystr = "  %s:  channel %d; " % (_params["name"], _chan)
            for _key, _val in _params.items():
                if _key != "name":
                    mystr += _key
                    try:
                        mystr += " %4d; " % int(_val)
                    except ValueError:
                        mystr += " " + _val + "; "
            print(mystr)
