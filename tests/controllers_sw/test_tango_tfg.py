# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.controllers.tango_tfg import TangoTfg2


@pytest.fixture()
def tfg(request, mocker):
    m = mocker.patch("tango.DeviceProxy")
    client = m.return_value
    client.acqStatus = "IDLE"
    client.armedStatus = "IDLE"
    client.maximumFrames = 2097152
    client.currentLap = 0
    client.currentFrame = 0
    client.startCount = 0
    client.command_inout_reply.return_value = 7
    client.read_frame.return_value = [1000, 12, 34, 56, 78, 90, 0, 0, 0]
    timer = TangoTfg2("test_tfg", {"url": "tfg/tango/1"})
    yield timer


def test_tango_tfg_init(tfg):
    assert tfg.cycles == 1
    assert tfg.external_start is False
    assert tfg.external_inhibit is False
    assert tfg.nbframes == 0
    assert tfg.acq_status == "IDLE"
    assert tfg.armed_status == "IDLE"
    assert tfg.maximum_frames == 2097152
    assert tfg.current_lap == 0
    assert tfg.current_frame == 0
    assert tfg.start_count == 0


def test_tango_tfg_timing_info(tfg):
    timing_info = {"framesets": [{"nb_frames": 7, "latency": 1e-07, "acq_time": 0.1}]}
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_with(
        "setupGroups", [0, 1, 7, 1e-07, 0.1, 0, 0, 0, 0, -1]
    )
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "framesets": [{"nb_frames": 7, "latency": 1e-07, "acq_time": 0.1}],
        "pauseTrigger": {"name": "Software", "period": "dead"},
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups", [0, 1, 7, 1e-07, 0.1, 0, 0, -1, 0, -1]
    )
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 4,
        "extInhibit": True,
        "framesets": [
            {"nb_frames": 5, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.1},
        ],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups", [12, 4, 7, 1e-07, 0.1, 0, 0, 0, 0, -1]
    )
    assert tfg.external_start is False
    assert tfg.external_inhibit is True
    assert tfg.nbframes == 7
    assert tfg.cycles == 4

    timing_info = {
        "cycles": 2,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 4, "latency": 1e-07, "acq_time": 0.5},
        ],
        "startTrigger": {"name": "TTLtrig0"},
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups", [10, 2, 3, 1e-07, 0.1, 0, 0, 0, 0, 4, 1e-07, 0.5, 0, 0, 0, 0, -1]
    )
    tfg._control.setupTrig.assert_called_once_with([130, 8, 0, 0, 0])
    assert tfg.external_start is True
    assert tfg.nbframes == 7
    assert tfg.cycles == 2

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 4, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {"name": "TTLtrig1", "period": "live"},
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            4,
            1e-07,
            0.1,
            0,
            0,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            2,
            1e-07,
            0.5,
            0,
            0,
            0,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.5},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {"name": "TTLtrig1", "period": "live", "trig_when": [-1]},
    }
    tfg._control.reset_mock()
    tfg._control.setupTrig.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            3,
            1e-07,
            0.5,
            0,
            0,
            0,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {"name": "TTLtrig1", "period": "live", "trig_when": [-1]},
    }
    tfg._control.reset_mock()
    tfg._control.setupTrig.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            2,
            1e-07,
            0.5,
            0,
            0,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {"name": "TTLtrig1", "period": "live", "trig_when": [4, 7]},
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            0,
            0,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            2,
            1e-07,
            0.5,
            0,
            0,
            0,
            0,
            1,
            1e-07,
            0.3,
            0,
            0,
            0,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {"name": "TTLtrig1", "period": "live", "trig_when": [-1]},
        "triggers": [{"name": "lancelot", "period": "live", "port": "UserOut2"}],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            4,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            4,
            0,
            9,
            2,
            1e-07,
            0.5,
            0,
            4,
            0,
            9,
            1,
            1e-07,
            0.3,
            0,
            4,
            0,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {
            "name": "TTLtrig1",
            "period": "dead",
            "trig_when": [-1],
            "edge": "Falling",
        },
        "triggers": [
            {
                "name": "lancelot",
                "period": "dead",
                "port": "UserOut2",
                "trig_when": [4, 7],
            }
        ],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            41,
            0,
            1,
            1e-07,
            0.3,
            4,
            0,
            41,
            0,
            2,
            1e-07,
            0.5,
            0,
            0,
            41,
            0,
            1,
            1e-07,
            0.3,
            4,
            0,
            41,
            0,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([128, 9, 0, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {
            "name": "TTLtrig1",
            "period": "both",
            "trig_when": [-1],
            "debounce": 0.2,
            "threshold": 0.5,
        },
        "triggers": [
            {
                "name": "lancelot",
                "period": "live",
                "port": "UserOut2",
                "trig_when": [4, 7],
            },
            {"name": "frelon", "period": "live", "port": "UserOut3", "trig_when": [4]},
        ],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            9,
            9,
            1,
            1e-07,
            0.3,
            0,
            12,
            9,
            9,
            2,
            1e-07,
            0.5,
            0,
            0,
            9,
            9,
            1,
            1e-07,
            0.3,
            0,
            4,
            9,
            9,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([160, 9, 0.2, 0, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {
            "name": "VarThrshld",
            "period": "both",
            "trig_when": [-1],
            "debounce": 0.2,
            "threshold": 0.5,
        },
        "triggers": [
            {
                "name": "lancelot",
                "period": "live",
                "port": "UserOut2",
                "trig_when": [4, 7],
            },
            {
                "name": "frelon",
                "period": "live",
                "port": "UserOut3",
                "trig_when": [4],
                "invert": True,
                "series_terminated": True,
            },
        ],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            16,
            16,
            1,
            1e-07,
            0.3,
            0,
            12,
            16,
            16,
            2,
            1e-07,
            0.5,
            0,
            0,
            16,
            16,
            1,
            1e-07,
            0.3,
            0,
            4,
            16,
            16,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([224, 16, 0.2, 0.5, 0])
    tfg._control.setupPort.assert_called_once_with([8, 8])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1

    timing_info = {
        "cycles": 1,
        "framesets": [
            {"nb_frames": 3, "latency": 1e-07, "acq_time": 0.1},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
            {"nb_frames": 2, "latency": 1e-07, "acq_time": 0.5},
            {"nb_frames": 1, "latency": 1e-07, "acq_time": 0.3},
        ],
        "startTrigger": {"name": "Software"},
        "pauseTrigger": {
            "name": "VarThrshld",
            "period": "both",
            "trig_when": [-1],
            "debounce": 0.0,
            "threshold": 0.5,
        },
        "triggers": [
            {
                "name": "lancelot",
                "period": "live",
                "port": "UserOut2",
                "trig_when": [4, 7],
            },
            {"name": "frelon", "period": "live", "port": "UserOut3", "trig_when": [4]},
        ],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.command_inout_asynch.assert_called_once_with(
        "setupGroups",
        [
            0,
            1,
            3,
            1e-07,
            0.1,
            0,
            0,
            16,
            16,
            1,
            1e-07,
            0.3,
            0,
            12,
            16,
            16,
            2,
            1e-07,
            0.5,
            0,
            0,
            16,
            16,
            1,
            1e-07,
            0.3,
            0,
            4,
            16,
            16,
            -1,
        ],
    )
    tfg._control.setupTrig.assert_called_once_with([196, 16, 0, 0.5, 0])
    assert tfg.external_start is False
    assert tfg.nbframes == 7
    assert tfg.cycles == 1


def test_tango_tfg_start(tfg, mocker):
    timing_info = {"framesets": [{"nb_frames": 7, "latency": 1e-07, "acq_time": 0.1}]}
    tfg.prepare(timing_info)
    tfg.start()
    tfg._control.clear.assert_called_once_with([0, 0, 0, tfg.maximum_frames, 1, 9])
    tfg._control.enable.assert_called_once_with()
    tfg._control.start.assert_called_once_with()

    #     tfg._control.reset_mock()
    #     mm = mocker.patch('gevent.sleep')
    #     timing_info = {
    #             'framesets': [{'nb_frames': 7, 'latency': 1e-07, 'acq_time': 0.1}],
    #             'startTrigger': {'name': 'TTLtrig0'}
    #             }
    #     tfg.prepare(timing_info)
    #     tfg.start()
    #     tfg._control.clear.assert_called_once_with([0, 0, 0, tfg.maximum_frames, 1, 9])
    #     tfg._control.enable.assert_called_once_with()
    #     tfg._control.arm.assert_called_once_with()

    tfg.stop()
    tfg._control.disable.assert_called_once_with()


def test_tango_tfg_read(tfg):
    expected = [1000, 12, 34, 56, 78, 90, 0, 0, 0]
    data = tfg.read_frame(1)
    tfg._control.read.assert_called_once_with([1, 0, 0, 1, 1, tfg.MAX_CHAN])
    for i, elem in enumerate(data):
        assert elem == expected[i]


def test_tango_tfg_scalers(tfg):
    timing_info = {"framesets": [{"nb_frames": 7, "latency": 1e-07, "acq_time": 0.1}]}
    tfg.prepare(timing_info)
    tfg._control.setupCCMode.assert_called_once_with(tfg.ScalerMode["Scaler64"])
    tfg._control.setupCCChan.assert_called_once_with(
        [tfg.ScalerOptions["count_rising_edges"], tfg.ALL_CHAN]
    )

    timing_info = {
        "framesets": [{"nb_frames": 7, "latency": 1e-07, "acq_time": 0.1}],
        "scalerMode": "Scaler64",
        "scalerChannels": [{"name": "ScalIn5", "option": "count_while_input_low"}],
    }
    tfg._control.reset_mock()
    tfg.prepare(timing_info)
    tfg._control.setupCCMode.assert_called_with(tfg.ScalerMode["Scaler64"])
    tfg._control.setupCCChan.assert_called_with(
        [tfg.ScalerOptions["count_while_input_low"], tfg.ScalerInput["ScalIn5"]]
    )
