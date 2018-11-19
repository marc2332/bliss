# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Usage:

    timing_info = {'cycles': 1,
                   'ccmode': 'Scaler64'
                   'framesets': [{'nb_frames': 30,
                                  'latency': 0.0000001,
                                  'acq_time': 0.1},
                                 {'nb_frames': 10,
                                  'latency': 0.0000001,
                                  'acq_time': 0.5},
                                 ],
                    'startTrigger': {'name': 'TTLtrig0',
                                     'edge': 'falling',
                                     'debounce': 0.0,
                                     'threshold': 0.0,
                                    },
                    'pauseTrigger': {'name': 'TTLtrig1',
                                     'trig_when': [ALL_FRAMES,],
                                     'period': 'dead',
                                     'edge': 'falling', # default = rising
                                     'debounce': 0.0,   # default
                                     'threshold': 0.0,  # default
                                     },
                    'triggers': [{'name': 'xspress3mini',
                                  'port': 'UserOut0',
                                  'trig_when': [ALL_FRAMES,],
                                  'period': 'live',
                                  'invert': False,
                                  'series_terminated': False},
                                 {'name': 'frelon',
                                  'port': 'UserOut1',
                                  'trig_when': [4,5,6,],
                                  'period': 'live',
                                  'invert': False,
                                  'series_terminated': False},
                                  ],
                    'scalerMode': 'Scaler64'
                    'scalerChannels': [{'name': 'ScalIn0',
                                        'option': 'count_rising_edges'}
                                       ]
                    }

    timer = TangoTfg2(name, config)
    timer.prepare(timing_info)
    timer.start()
"""
from __future__ import absolute_import
from __future__ import print_function

import gevent

import tango
import tango.gevent


class TangoTfg2(object):
    RISING_EDGE = 2
    ALL_CHAN = -1
    MAX_CHAN = 9
    ALL_FRAMES = -1

    TriggerNameList = {
        "Software": -1,
        "NoPause": 0,
        "BMTrigger": 1,
        "ADCchan0": 2,
        "ADCchan1": 3,
        "ADCchan2": 4,
        "ADCchan3": 5,
        "ADCchan4": 6,
        "ADCchan5": 7,
        "TTLtrig0": 8,
        "TTLtrig1": 9,
        "TTLtrig2": 10,
        "TTLtrig3": 11,
        "LVDSLemo": 12,
        "TFG cable 1": 13,
        "TFGCable2": 14,
        "TFGcable3": 15,
        "VarThrshld": 16,
    }
    TriggerOutputs = {
        "UserOut0": 1,
        "UserOut1": 2,
        "UserOut2": 4,
        "UserOut3": 8,
        "UserOut4": 16,
        "UserOut5": 32,
        "UserOut6": 64,
        "UserOut7": 128,
    }
    Group = {
        "help": 1,
        "ext_start": 2,
        "ext_inh": 4,
        "cycles": 8,
        "file": 16,
        "no_min_20us": 32,
        "silent": 64,
        "sequence": 128,
        "auto_rearm": 256,
        "ext_falling": 512,
    }
    TrigOptions = {
        "help": 1,
        "start": 2,
        "pause": 4,
        "pause_next_dead": 8,
        "falling": 16,
        "debounce": 32,
        "threshold": 64,
        "now": 128,
        "raw": 256,
        "alternate": 512,
    }
    ScalerInput = {
        "ScalIn0": 0,
        "ScalIn1": 1,
        "ScalIn2": 2,
        "ScalIn3": 3,
        "ScalIn4": 4,
        "ScalIn5": 5,
        "ScalIn6": 6,
        "ScalIn7": 7,
    }
    ScalerMode = {
        "All": 1,
        "Scaler64": 2,  # 64 bit scalers
        "Adcs6": 4,
        "ShortMixed": 8,  # (Hit, Live, 6 ADCs/Hit, Live, 4 Scalers, 4 ADCs)
        "ShortScalers": 16,  # (Hit, Live, Scal 0..3 64 bot, Scal4..7 32 bit)
        "Adcs8": 32,  # (8 ADCs)
    }
    ScalerOptions = {
        "count_while_input_high": 1,
        "count_rising_edges": 2,
        "count_while_input_low": 4,
    }

    def __init__(self, name, config):
        self.name = name
        tango_uri = config.get("tango_uri")
        self._control = None
        self.__external_start = False
        self.__external_inhibit = False
        self.__cycles = 1
        self.__nframes = 0
        try:
            self._control = tango.DeviceProxy(tango_uri)
        except tango.DevFailed, traceback:
            last_error = traceback[-1]
            print("%s: %s" % (tango_uri, last_error["desc"]))
            self._control = None
        else:
            try:
                self._control.ping()
                self._control.clearStarts()
            except tango.ConnectionFailed:
                self._control = None

    #                raise RuntimeError("Connection error")

    @property
    def current_lap(self):
        return self._control.currentLap

    @property
    def current_frame(self):
        return self._control.currentFrame

    @property
    def cycles(self):
        return self.__cycles

    @property
    def acq_status(self):
        return self._control.acqStatus

    @property
    def armed_status(self):
        return self._control.armedStatus

    @property
    def start_count(self):
        return self._control.startCount

    @property
    def maximum_frames(self):
        return self._control.maximumFrames

    @property
    def external_start(self):
        return self.__external_start

    @property
    def external_inhibit(self):
        return self.__external_inhibit

    @property
    def nbframes(self):
        return self.__nframes

    def prepare(self, timing_info):
        self._control.init()
        self.clear()
        self.__cycles = timing_info.get("cycles", 1)
        self.__external_inhibit = timing_info.get("extInhibit", False)

        start_trigger = timing_info.get("startTrigger", {"name": "Software"})
        self.set_start_trigger(
            start_trigger["name"],
            start_trigger.get("edge", "rising"),
            start_trigger.get("debounce", 0.0),
            start_trigger.get("threshold", 0.0),
        )

        pause_trigger = timing_info.get("pauseTrigger", {"name": "Software"})
        if pause_trigger["name"]:
            self.set_pause_trigger(
                pause_trigger["name"],
                pause_trigger.get("edge", "rising"),
                pause_trigger.get("debounce", 0.0),
                pause_trigger.get("threshold", 0.0),
            )

        frame_list = []
        frame_count = 0
        dead_pause = 0
        live_pause = 0
        trigger = self.TriggerNameList[pause_trigger["name"]]
        edge = pause_trigger.get("edge", "rising")
        if pause_trigger.get("period", None) == "dead":
            dead_pause = trigger
            if edge != "rising":  # then it's falling edge
                dead_pause |= 32
        elif pause_trigger.get("period", None) == "live":
            live_pause = trigger
            if edge != "rising":  # then it's falling edge
                live_pause |= 32
        elif pause_trigger.get("period", None) == "both":
            dead_pause = trigger
            live_pause = trigger
            if edge != "rising":  # then it's falling edge
                dead_pause |= 32
                live_pause |= 32

        inversion = 0
        drive_strength = 0
        for frameset in timing_info["framesets"]:
            frame_count += frameset["nb_frames"]
            if (
                pause_trigger.get("trig_when", [self.ALL_FRAMES]) == [self.ALL_FRAMES]
            ) or (
                frameset["nb_frames"] == 1
                and frame_count in pause_trigger.get("trig_when", [])
            ):
                dpause = dead_pause
                lpause = live_pause
            else:
                dpause = 0
                lpause = 0

            live_port = 0
            dead_port = 0
            inversion = 0
            drive_strength = 0
            for trigger_out in timing_info.get("triggers", []):
                port = trigger_out["port"]
                if trigger_out.get("invert", False) is True:
                    inversion |= self.TriggerOutputs[port]
                if trigger_out.get("series_terminated", False) is True:
                    drive_strength |= self.TriggerOutputs[port]
                if (
                    trigger_out.get("trig_when", self.ALL_FRAMES) == self.ALL_FRAMES
                ) or (
                    frameset["nb_frames"] == 1
                    and frame_count in trigger_out.get("trig_when", [])
                ):
                    trig = self.TriggerOutputs[trigger_out["port"]]
                    if trigger_out.get("period", None) == "dead":
                        dead_port |= trig
                    elif trigger_out.get("period", None) == "live":
                        live_port |= trig

            frame_list.extend(
                (
                    frameset["nb_frames"],
                    frameset["latency"],
                    frameset["acq_time"],
                    dead_port,
                    live_port,
                    dpause,
                    lpause,
                )
            )
        self.__setup_groups(self.__compress(frame_list))
        self.__setup_port(inversion, drive_strength)
        self._control.setupVeto(
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        )
        self.__setup_scaler_channels(timing_info)

    def start(self):
        self.enable()
        if self.__external_start:
            self._control.arm()
            while self.armed_status != "EXT-ARMED":
                gevent.sleep(0.05)
        else:
            self._control.start()

    def stop(self):
        self.disable()
        self._control.stop()

    def resume(self):
        self._control.cont()

    def clear(self):
        self._control.clearStarts()
        self._control.clear([0, 0, 0, self.maximum_frames, 1, self.MAX_CHAN])

    def read_frame(self, frame):
        return self._control.read([frame, 0, 0, 1, 1, self.MAX_CHAN])

    def enable(self):
        self._control.enable()

    def disable(self):
        self._control.disable()

    def __compress(self, framelist):
        compressed = []
        for i in range(0, len(framelist), 7):
            if i == 0:
                last = framelist[0:7]
            elif framelist[i + 1 : i + 7] == last[1:7]:
                last[0] += framelist[i]
            else:
                compressed.extend(last)
                last = framelist[i : i + 7]
        compressed.extend(last)
        return compressed

    def __setup_groups(self, framesets):
        args = []
        qualifiers = 0
        if self.__cycles > 1:
            qualifiers |= self.Group.get("cycles")
        if self.__external_start:
            qualifiers |= self.Group.get("ext_start")
        if self.__external_inhibit:
            qualifiers |= self.Group.get("ext_inh")
        args.append(qualifiers)
        args.append(self.__cycles)
        args.extend(framesets)
        args.append(-1)
        self._control.set_timeout_millis(10000)
        print(args)
        id = self._control.command_inout_asynch("setupGroups", args)
        self.__nframes = self._control.command_inout_reply(id, 8000)

    def __setup_port(self, invert, drive_strength):
        # invert 8bit inversion 1 to invert
        # drive_strength 8bit drive strength 0=> full drive, 1=> series terminated
        self._control.setupPort([invert & 0xff, drive_strength & 0xff])

    def set_start_trigger(
        self, trigger_name, edge="rising", debounce=0.0, threshold=0.0
    ):
        self.__setup_trig("start", trigger_name, edge, debounce, threshold)

    def set_pause_trigger(
        self, trigger_name, edge="rising", debounce=0.0, threshold=0.0
    ):
        self.__setup_trig("pause", trigger_name, edge, debounce, threshold)

    def __setup_trig(self, action, trigger_name, edge, debounce, threshold):
        trigger_nb = self.TriggerNameList.get(trigger_name)
        args = [
            self.TrigOptions.get("now"),
            trigger_nb,  # trigger input number 1..16
            0,  # debounce value
            0,  # threshold value
            0,  # not used (Alternate trigger)
        ]
        if trigger_name == "Software":
            if action == "start":
                self.__external_start = False
        else:
            if action == "start":
                args[0] |= self.TrigOptions.get(action)
                self.__external_start = True
                if edge != "rising":  # then it's falling edge
                    args[0] |= self.TrigOptions.get("falling")
            if debounce != 0.0:
                if trigger_nb == 16 and threshold != 0.0:
                    args[0] |= self.TrigOptions.get("debounce") | self.TrigOptions.get(
                        "threshold"
                    )
                    args[2] = debounce
                    args[3] = threshold
                else:
                    args[0] |= self.TrigOptions.get("debounce")
                    args[2] = debounce
            else:
                if trigger_nb == 16 and threshold != 0.0:
                    args[0] |= self.TrigOptions.get("threshold")
                    args[3] = threshold
            print(args)
            self._control.setupTrig(args)

    def __setup_scaler_channels(self, timing_info):
        scaler_mode = timing_info.get("scalerMode", "Scaler64")
        self._control.setupCCMode(self.ScalerMode[scaler_mode])

        scaler_channels = timing_info.get("scalerChannels", self.ALL_CHAN)
        if scaler_channels == self.ALL_CHAN:
            self._control.setupCCChan(
                [self.ScalerOptions["count_rising_edges"], self.ALL_CHAN]
            )
        else:
            # set all channels to default in case options for every channel not specified
            self._control.setupCCChan(
                [self.ScalerOptions["count_rising_edges"], self.ALL_CHAN]
            )
            for channel in scaler_channels:
                self._control.setupCCChan(
                    [
                        self.ScalerOptions[channel.get("option", "count_rising_edges")],
                        self.ScalerInput[channel.get("name", self.ALL_CHAN)],
                    ]
                )
