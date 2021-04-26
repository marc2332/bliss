# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.comm.util import TCP, get_comm
from bliss.comm.tcp import SocketTimeout
from bliss.common.axis import AxisState
from bliss.common.encoder import Encoder, lazy_init
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss import global_map
from bliss.common.logtools import log_info, log_debug, log_debug_data

import string
import time
import gevent
import gevent.lock
import enum
from collections import namedtuple


@enum.unique
class AerotechParameter(enum.IntEnum):
    """ Aerotech Parameter definition
        """

    AxisType = 0
    ReverseMotionDirection = 1
    CountsPerUnit = 2
    ServoRate = 3
    ServoSetup = 4
    GainKpos = 5
    GainKi = 6
    GainKp = 7
    GainVff = 8
    GainAff = 9
    GainKv = 10
    GainKpi = 11
    ServoFilter0CoeffN0 = 12
    ServoFilter0CoeffN1 = 13
    ServoFilter0CoeffN2 = 14
    ServoFilter0CoeffD1 = 15
    ServoFilter0CoeffD2 = 16
    ServoFilter1CoeffN0 = 17
    ServoFilter1CoeffN1 = 18
    ServoFilter1CoeffN2 = 19
    ServoFilter1CoeffD1 = 20
    ServoFilter1CoeffD2 = 21
    AmplifierDeadtime = 22
    RolloverCounts = 23
    CurrentGainKi = 24
    CurrentGainKp = 25
    FaultMask = 26
    FaultMaskDisable = 27
    FaultMaskDecel = 28
    EnableBrakeControl = 29
    FaultMaskOutput = 30
    ESTOPFaultInput = 31
    PositionErrorThreshold = 32
    AverageCurrentThreshold = 33
    AverageCurrentTime = 34
    VelocityCommandThreshold = 35
    VelocityErrorThreshold = 36
    SoftwareLimitLow = 37
    SoftwareLimitHigh = 38
    MaxCurrentClamp = 39
    InPositionDistance = 40
    MotorType = 41
    CyclesPerRev = 42
    CountsPerRev = 43
    CommutationOffset = 44
    AutoMsetTime = 45
    AutoMsetCurrent = 46
    PositionFeedbackType = 47
    PositionFeedbackChannel = 48
    VelocityFeedbackType = 49
    VelocityFeedbackChannel = 50
    EncoderMultiplicationFactor = 51
    EncoderSineGain = 52
    EncoderSineOffset = 53
    EncoderCosineGain = 54
    EncoderCosineOffset = 55
    EncoderPhase = 56
    GantryMasterAxis = 57
    LimitDecelDistance = 59
    LimitDebounceTime = 60
    EndOfTravelLimitSetup = 61
    BacklashDistance = 62
    FaultOutputSetup = 63
    FaultOutputState = 64
    IOSetup = 65
    BrakeOutput = 66
    EncoderDivider = 67
    ExternalFaultDigitalInput = 68
    BrakeDisableDelay = 69
    MaxJogDistance = 70
    DefaultSpeed = 71
    DefaultRampRate = 72
    AbortDecelRate = 73
    HomeType = 74
    HomeSetup = 75
    HomeSpeed = 76
    HomeOffset = 77
    HomeRampRate = 78
    DefaultWaitMode = 79
    DefaultSCurve = 80
    DataCollectionPoints = 81
    StepperResolution = 83
    StepperRunningCurrent = 84
    StepperHoldingCurrent = 85
    StepperVerificationSpeed = 86
    LimitDebounceDistance = 87
    ServoFilter2CoeffN0 = 88
    ServoFilter2CoeffN1 = 89
    ServoFilter2CoeffN2 = 90
    ServoFilter2CoeffD1 = 91
    ServoFilter2CoeffD2 = 92
    ServoFilter3CoeffN0 = 93
    ServoFilter3CoeffN1 = 94
    ServoFilter3CoeffN2 = 95
    ServoFilter3CoeffD1 = 96
    ServoFilter3CoeffD2 = 97
    GearCamSource = 98
    GearCamIndex = 99
    GearCamScaleFactor = 100
    GearCamAnalogDeadband = 105
    PrintBufferSize = 106
    SerialPort0XonCharacter = 109
    SerialPort0XoffCharacter = 110
    SerialPort0BaudRate = 111
    SerialPort0Setup = 112
    TaskExecutionSetup = 113
    CodeSize = 114
    DataSize = 115
    StackSize = 116
    AutoRunProgram = 118
    MaxJogSpeed = 123
    GlobalIntegers = 124
    GlobalDoubles = 125
    DecimalPlaces = 126
    TaskErrorAbortAxes = 127
    CalibrationFile1D = 128
    UnitsName = 129
    Socket2RemoteIPAddress = 130
    Socket2Port = 131
    Socket2Setup = 132
    Socket2TransmissionSize = 133
    Socket3RemoteIPAddress = 134
    Socket3Port = 135
    Socket3Setup = 136
    Socket3TransmissionSize = 137
    Socket2Timeout = 138
    Socket3Timeout = 139
    UserInteger0 = 141
    UserInteger1 = 142
    UserDouble0 = 143
    UserDouble1 = 144
    UserString0 = 145
    UserString1 = 146
    EnDatEncoderSetup = 147
    EnDatEncoderResolution = 148
    EnDatEncoderTurns = 149
    CommandSetup = 150
    SerialPort1XonCharacter = 152
    SerialPort1XoffCharacter = 153
    SerialPort1BaudRate = 154
    SerialPort1Setup = 155
    RequiredAxes = 156
    JoystickInput1MinVoltage = 157
    JoystickInput1MaxVoltage = 158
    JoystickInput1Deadband = 159
    JoystickInput0MinVoltage = 160
    JoystickInput0MaxVoltage = 161
    JoystickInput0Deadband = 162
    JoystickLowSpeed = 163
    JoystickHighSpeed = 164
    JoystickSetup = 165
    HomePositionSet = 166
    TaskTerminationAxes = 167
    TaskStopAbortAxes = 168
    CalibrationFile2D = 169
    FaultMaskDisableDelay = 170
    DefaultCoordinatedSpeed = 171
    DefaultCoordinatedRampRate = 172
    DefaultDependentCoordinatedRampRate = 173
    GpibTerminatingCharacter = 174
    GpibPrimaryAddress = 175
    GpibParallelResponse = 176
    CommandTerminatingCharacter = 177
    CommandSuccessCharacter = 178
    CommandInvalidCharacter = 179
    CommandFaultCharacter = 180
    FaultAbortAxes = 182
    HarmonicCancellation0Type = 185
    HarmonicCancellation0Period = 186
    HarmonicCancellation0Gain = 188
    HarmonicCancellation0Phase = 189
    HarmonicCancellation1Type = 190
    HarmonicCancellation1Period = 191
    HarmonicCancellation1Gain = 193
    HarmonicCancellation1Phase = 194
    HarmonicCancellation2Type = 195
    HarmonicCancellation2Period = 196
    HarmonicCancellation2Gain = 198
    HarmonicCancellation2Phase = 199
    CommandTimeout = 202
    CommandTimeoutCharacter = 203
    ResolverReferenceGain = 204
    ResolverSetup = 205
    ResolverReferencePhase = 206
    SoftwareLimitSetup = 210
    SSINet1Setup = 211
    SSINet2Setup = 212
    EmulatedQuadratureDivider = 213
    HarmonicCancellation3Type = 214
    HarmonicCancellation3Period = 215
    HarmonicCancellation3Gain = 217
    HarmonicCancellation3Phase = 218
    HarmonicCancellation4Type = 219
    HarmonicCancellation4Period = 220
    HarmonicCancellation4Gain = 222
    HarmonicCancellation4Phase = 223
    EnhancedThroughputChannel = 224
    EnhancedThroughputGain = 225
    HarmonicCancellationSetup = 226
    EnhancedThroughputCurrentClamp = 227
    Analog0Filter0CoeffN0 = 228
    Analog0Filter0CoeffN1 = 229
    Analog0Filter0CoeffN2 = 230
    Analog0Filter0CoeffD1 = 231
    Analog0Filter0CoeffD2 = 232
    Analog0Filter1CoeffN0 = 233
    Analog0Filter1CoeffN1 = 234
    Analog0Filter1CoeffN2 = 235
    Analog0Filter1CoeffD1 = 236
    Analog0Filter1CoeffD2 = 237
    Analog1Filter0CoeffN0 = 238
    Analog1Filter0CoeffN1 = 239
    Analog1Filter0CoeffN2 = 240
    Analog1Filter0CoeffD1 = 241
    Analog1Filter0CoeffD2 = 242
    Analog1Filter1CoeffN0 = 243
    Analog1Filter1CoeffN1 = 244
    Analog1Filter1CoeffN2 = 245
    Analog1Filter1CoeffD1 = 246
    Analog1Filter1CoeffD2 = 247
    GlobalStrings = 248
    DefaultCoordinatedRampMode = 249
    DefaultCoordinatedRampTime = 250
    DefaultCoordinatedRampDistance = 251
    DefaultRampMode = 252
    DefaultRampTime = 253
    DefaultRampDistance = 254
    ServoFilterSetup = 255
    FeedbackSetup = 256
    EncoderMultiplierSetup = 257
    FaultSetup = 258
    ThresholdScheduleSetup = 259
    ThresholdRegion2High = 260
    ThresholdRegion2Low = 261
    ThresholdRegion3GainKpos = 262
    ThresholdRegion3GainKp = 263
    ThresholdRegion3GainKi = 264
    ThresholdRegion3GainKpi = 265
    ThresholdRegion4High = 266
    ThresholdRegion4Low = 267
    ThresholdRegion5GainKpos = 268
    ThresholdRegion5GainKp = 269
    ThresholdRegion5GainKi = 270
    ThresholdRegion5GainKpi = 271
    DynamicScheduleSetup = 272
    DynamicGainKposScale = 273
    DynamicGainKpScale = 274
    DynamicGainKiScale = 275
    ServoFilter4CoeffN0 = 276
    ServoFilter4CoeffN1 = 277
    ServoFilter4CoeffN2 = 278
    ServoFilter4CoeffD1 = 279
    ServoFilter4CoeffD2 = 280
    ServoFilter5CoeffN0 = 281
    ServoFilter5CoeffN1 = 282
    ServoFilter5CoeffN2 = 283
    ServoFilter5CoeffD1 = 284
    ServoFilter5CoeffD2 = 285
    ServoFilter6CoeffN0 = 286
    ServoFilter6CoeffN1 = 287
    ServoFilter6CoeffN2 = 288
    ServoFilter6CoeffD1 = 289
    ServoFilter6CoeffD2 = 290
    ServoFilter7CoeffN0 = 291
    ServoFilter7CoeffN1 = 292
    ServoFilter7CoeffN2 = 293
    ServoFilter7CoeffD1 = 294
    ServoFilter7CoeffD2 = 295
    LinearAmpMaxPower = 296
    LinearAmpDeratingFactor = 297
    LinearAmpBusVoltage = 298
    MotorResistance = 299
    MotorBackEMFConstant = 300
    GantrySetup = 302
    RolloverMode = 303
    EmulatedQuadratureChannel = 305
    ResolverCoarseChannel = 306
    ResolverFeedbackRatio = 307
    ResolverFeedbackOffset = 308
    BrakeEnableDelay = 309
    InPositionTime = 319
    StaticFrictionCompensation = 324
    ExternalFaultAnalogInput = 424
    ExternalFaultThreshold = 425
    DisplayAxes = 426
    DefaultDependentCoordinatedSpeed = 427
    AnalogFilterSetup = 482
    DefaultRampType = 485
    ModbusMasterSlaveIPAddress = 489
    ModbusMasterSlavePort = 490
    ModbusMasterSlaveID = 491
    ModbusMasterInputWords = 492
    ModbusMasterOutputWords = 493
    ModbusMasterInputBits = 494
    ModbusMasterOutputBits = 495
    ModbusMasterSetup = 496
    ModbusMasterVirtualInputs = 499
    ModbusMasterVirtualOutputs = 500
    ModbusMasterOutputWordsSections = 501
    ModbusMasterOutputBitsSections = 502
    ModbusMasterRWReadOffset = 503
    ModbusMasterInputWordsOffset = 504
    ModbusMasterOutputWordsOffset = 505
    ModbusMasterInputBitsOffset = 506
    ModbusMasterOutputBitsOffset = 507
    ModbusMasterStatusWordsOffset = 508
    ModbusMasterStatusBitsOffset = 509
    ModbusMasterVirtualInputsOffset = 510
    ModbusMasterVirtualOutputsOffset = 511
    ModbusMasterRWWriteOffset = 512
    ModbusMasterFunctions = 513
    ModbusMasterSlaveType = 514
    ModbusSlaveUnitID = 516
    ModbusSlaveInputWords = 517
    ModbusSlaveOutputWords = 518
    ModbusSlaveInputBits = 519
    ModbusSlaveOutputBits = 520
    ModbusSlaveInputWordsOffset = 521
    ModbusSlaveOutputWordsOffset = 522
    ModbusSlaveInputBitsOffset = 523
    ModbusSlaveOutputBitsOffset = 524
    ModbusSlaveRWReadOffset = 525
    ModbusSlaveRWWriteOffset = 526
    CurrentOffsetA = 662
    CurrentOffsetB = 663
    FaultAckMoveOutOfLimit = 665
    CommandShaperSetup = 666
    CommandShaperTime00 = 667
    CommandShaperTime01 = 668
    CommandShaperTime02 = 669
    CommandShaperTime03 = 670
    CommandShaperTime04 = 671
    CommandShaperTime05 = 672
    CommandShaperTime06 = 673
    CommandShaperTime07 = 674
    CommandShaperTime08 = 675
    CommandShaperTime09 = 676
    CommandShaperTime10 = 677
    CommandShaperTime11 = 678
    CommandShaperTime12 = 679
    CommandShaperTime13 = 680
    CommandShaperTime14 = 681
    CommandShaperTime15 = 682
    CommandShaperCoeff00 = 683
    CommandShaperCoeff01 = 684
    CommandShaperCoeff02 = 685
    CommandShaperCoeff03 = 686
    CommandShaperCoeff04 = 687
    CommandShaperCoeff05 = 688
    CommandShaperCoeff06 = 689
    CommandShaperCoeff07 = 690
    CommandShaperCoeff08 = 691
    CommandShaperCoeff09 = 692
    CommandShaperCoeff10 = 693
    CommandShaperCoeff11 = 694
    CommandShaperCoeff12 = 695
    CommandShaperCoeff13 = 696
    CommandShaperCoeff14 = 697
    CommandShaperCoeff15 = 698
    CommandShaper0Type = 703
    CommandShaper0Frequency = 704
    CommandShaper0Damping = 705
    CommandShaper1Type = 706
    CommandShaper1Frequency = 707
    CommandShaper1Damping = 708
    ResoluteEncoderSetup = 715
    ResoluteEncoderResolution = 716
    ResoluteEncoderUserResolution = 717
    AutofocusInput = 721
    AutofocusTarget = 722
    AutofocusDeadband = 723
    AutofocusGainKi = 724
    AutofocusGainKp = 725
    AutofocusLimitLow = 726
    AutofocusLimitHigh = 727
    AutofocusSpeedClamp = 728
    AutofocusHoldInput = 729
    AutofocusSetup = 730
    ExternalSyncFrequency = 731
    GainPff = 762
    AutofocusInitialRampTime = 763
    SoftwareExternalFaultInput = 765
    AutofocusGainKi2 = 769
    EnDatEncoderIncrementalResolution = 770
    MarkerSearchThreshold = 771
    GainKd1 = 779
    GainKp1 = 780
    VelocityCommandThresholdBeforeHome = 781
    InPosition2Distance = 789
    InPosition2Time = 790
    StepperRunningCurrentDelay = 791
    ExternalVelocityAverageTime = 792
    Class1InputIntegers = 794
    Class1InputIntegersOffset = 795
    Class1OutputIntegers = 796
    Class1OutputIntegersOffset = 797
    Class1InputDoubles = 798
    Class1InputDoublesOffset = 799
    Class1OutputDoubles = 800
    Class1OutputDoublesOffset = 801
    AbsoluteFeedbackOffset = 802
    PiezoSetup = 803
    CapSensorFilterLength = 804
    EnhancedTrackingScale = 805
    EnhancedTrackingBandwidth = 806
    Analog0InputOffset = 807
    Analog1InputOffset = 808
    Analog2InputOffset = 809
    Analog3InputOffset = 810
    EnhancedTrackingSetup = 811
    WebServerSetup = 812
    WebServerPort = 813
    EncoderMarkerAlignment = 814
    EncoderRadiusThresholdLow = 815
    EncoderRadiusThresholdHigh = 816
    GainKsi1 = 817
    GainKsi2 = 818
    PiezoVoltsPerUnit = 819
    PiezoVoltageClampLow = 820
    PiezoVoltageClampHigh = 821
    PiezoSlewRateClamp = 822
    PiezoDefaultServoState = 823
    FeedforwardAdvance = 824
    CapSensorSetup = 826
    CapSensorThresholdLow = 828
    CapSensorThresholdHigh = 829
    RequiredStageSerialNumber = 832
    StepperDampingGain = 848
    StepperDampingCutoffFrequency = 849


class AerotechStatus(object):
    """ Utility class to decode aerotech 
        axis fault and axis status
        used by Aerotech controller class
    """

    def __init__(self, value, bitdef):
        self._bitdef = bitdef
        self._valdict = dict([(name, False) for name, bitidx in self._bitdef])
        self.set(value)

    def set(self, value):
        self._value = value
        for name, bitidx in self._bitdef:
            self._valdict[name] = bool(value & (1 << bitidx))

    def get(self):
        return self._value

    def __str__(self):
        stastr = ""
        for name, bitidx in self._bitdef:
            stastr += " * %20.20s = %s\n" % (name, self._valdict[name])
        return stastr

    def __getattr__(self, name):
        value = self._valdict.get(name, None)
        if value is None:
            raise ValueError("Unknown aerotech status field [%s]" % name)
        return value


class Aerotech(Controller):
    """
    Aerotech motor controller

    configuration example:
    - class: aerotech
      tcp:
        url: id15aero1
      axes:
        - name: rot
          aero_name: X
          steps_per_unit: 26222.2
          velocity: 200
          acceleration: 100
      encoder:
        - name: rot_enc
          aero_name: X

    standard functionnalilies:
    - standard moves
    - NO set dial position
    - velocity / acceleration
    - homing procedure
    - jog mode
    - encoder reading

    aerotech specific functionnalities:
    - set/get/dump aerotech parameters

    additionnal states:
    - HOMEDONE : when homing has been performed
    - EXTDISABLE : external signal input does not allow motor movement
    - EXTSTOP : external emergency stop signal has disabled motor
    The external input/stop signals has to be configured on the controller
    via aerotech software.

    notes:
    - axis configuration has to be done via aerotech software
    - socket ascii communication has to be activated on controller via aerotech software
    - default tcp port 8000 is used if not specified
    - velocity and acceleration are mandatory and
      always set on controller. The velocity and
      acceleration are not read from controller.
    """

    CMD_TERM = "\n"
    RET_SUCCESS = "%"
    RET_INVALID = "!"
    RET_FAULT = "#"
    RET_TIMEOUT = "$"

    AXIS_STATUS_BITS = (
        ("Enabled", 0),
        ("Homed", 1),
        ("InPosition", 2),
        ("MoveActive", 3),
        ("AccelPhase", 4),
        ("DecelPhase", 5),
        ("PositionCapture", 6),
        ("CurrentClamp", 7),
        ("BrakeOutput", 8),
        ("MotionDirection", 9),
        ("MasterSlaveControl", 10),
        ("CalActive", 11),
        ("CalEnabled", 12),
        ("JoystickControl", 13),
        ("Homing", 14),
        ("MasterSuppress", 15),
        ("GantryActive", 16),
        ("GantryMaster", 17),
        ("AutofocusActive", 18),
        ("CommandFilterDone", 19),
        ("InPosition2", 20),
        ("ServoControl", 21),
        ("PositiveLimit", 22),
        ("NegativeLimit", 23),
        ("HomeLimit", 24),
        ("MarkerInput", 25),
        ("HallAInput", 26),
        ("HallBInput", 27),
        ("HallCInput", 28),
        ("SineEncoderError", 29),
        ("CosineEncoderError", 30),
        ("EmergencyStop", 31),
    )

    AXIS_FAULT_BITS = (
        ("PositionError", 0),
        ("OverCurrent", 1),
        ("PositiveHardLimit", 2),
        ("NegativeHardLimit", 3),
        ("PositiveSoftLimit", 4),
        ("NegativeSoftLimit", 5),
        ("AmplifierFault", 6),
        ("PositionFbk", 7),
        ("VelocityFbk", 8),
        ("HallSensor", 9),
        ("MaxVelocity", 10),
        ("EmergencyStop", 11),
        ("VelocityError", 12),
        ("ExternalInput", 15),
        ("MotorTemperature", 17),
        ("AmplifierTemperature", 18),
        ("Encoder", 19),
        ("Communication", 20),
        ("FeedbackScaling", 23),
        ("MarkerSearch", 24),
        ("VoltageClamp", 27),
        ("PowerSupply", 28),
        ("Internal", 30),
    )

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        config = self.config.config_dict
        opt = {"port": 8000, "eol": "\n"}
        self._comm = get_comm(config, ctype=TCP, **opt)

        global_map.register(self, children_list=[self._comm])

        self._lock = gevent.lock.Semaphore()

    def initialize(self):
        self._aero_axis = {}
        self._aero_speed = {}
        self._aero_acc = {}
        self._aero_enc = {}
        self._internal_divider = {}
        self._output_divider = {}
        self._is_moving = {}
        self._aero_state = AxisState()
        self._aero_state.create_state("EXTDISABLE", "External disable signal")
        self._aero_state.create_state("EXTSTOP", "External stop signal")
        self._aero_state.create_state("HOMEDONE", "Homing done")

    def initialize_hardware(self):
        log_debug(self, "initialize_hardware")
        self.raw_write("ACKNOWLEDGEALL")
        self.raw_write("RAMP MODE RATE")
        self.raw_write("WAIT MODE NOWAIT")

    def initialize_axis(self, axis):
        log_debug(self, "initialize_axis %s", axis.name)
        if axis.name not in self._aero_axis.keys():
            aero_name = axis.config.get("aero_name", str, "")
            if aero_name in self._aero_axis.values():
                others = [
                    name
                    for name in self._aero_axis
                    if self._aero_axis[name] == aero_name
                ]
                raise ValueError(
                    "Aero Axis [%s] already defined for [%s]"
                    % (aero_name, ",".join(others))
                )
            self._aero_axis[axis.name] = aero_name

    def initialize_hardware_axis(self, axis):
        log_debug(self, "initilize_hardware_axis %s", axis.name)
        self.set_on(axis)
        self.get_encoder_output_divider(axis)
        self.get_encoder_internal_divider(axis)

    def close(self):
        if self._comm:
            self._comm.close()

    def raw_write(self, cmd):
        log_debug_data(self, "SEND", cmd)
        send_cmd = cmd + self.CMD_TERM
        with self._comm.lock:
            reply = self._comm.write_read(send_cmd.encode(), size=1)
        reply = reply.decode()
        log_debug_data(self, "GET", reply)
        self._check_reply_code(reply, cmd)

    def _check_reply_code(self, reply, cmd):
        if reply != self.RET_SUCCESS:
            if reply == self.RET_INVALID:
                raise ValueError("Aero Invalid command [%s]" % cmd)
            elif reply == self.RET_FAULT:
                raise ValueError("Aero Command error [%s]" % cmd)
            elif reply == self.RET_TIMEOUT:
                raise ValueError("Aero Timeout on command [%s]" % cmd)
            else:
                raise ValueError("Aero Unknown command error")
        return 1

    def raw_write_read(self, cmd):
        with self._comm.lock:
            self.raw_write(cmd)
            reply = self._comm.readline()
        reply = reply.decode()
        log_debug_data(self, "READ", reply)
        return reply

    def _aero_name(self, axis):
        aero_axis = self._aero_axis.get(axis.name, None)
        if aero_axis is None:
            raise ValueError("Aerotech axis [%s] not initialised" % axis.name)
        return aero_axis

    def _cmd(self, cmd, axis, *cmd_args, reply=True):
        aero_name = self._aero_name(axis)
        if aero_name:
            args = [aero_name] + list(cmd_args)
        else:
            args = cmd_args
        if reply:
            # args are comma-separated when asking the controller
            cmd_args = f"({','.join(map(str,args))})"
        else:
            # args are space-separated when sending a command
            cmd_args = f"{' '.join(map(str, args))}"
        return f'{cmd}{"" if reply else " "}{cmd_args}'

    def _cmd_no_reply(self, *args):
        return self._cmd(*args, reply=False)

    def _axis_from_aeroname(self, aeroname):
        for (axis_name, aero_type) in self._aero_axis.items():
            if aero_type == aeroname:
                return self.axes[axis_name]
        raise ValueError("No aerotech axis configured for [%s]" % aeroname)

    def clear_error(self, axis):
        self.raw_write(self._cmd_no_reply("FAULTACK", axis))

    def read_status(self, axis):
        with self._lock:
            try:
                return self.__try_read_status(axis)
            except SocketTimeout:
                log_info(self, "Retry on read_status SocketTimeout on ", axis.name)
                self._comm.flush()
                return self.__try_read_status(axis)

    def __try_read_status(self, axis):
        status = self.raw_write_read(self._cmd("AXISSTATUS", axis))
        axis_status = AerotechStatus(int(status), self.AXIS_STATUS_BITS)

        fault = self.raw_write_read(self._cmd("AXISFAULT", axis))
        axis_fault = AerotechStatus(int(fault), self.AXIS_FAULT_BITS)

        if int(fault) > 0 and not axis_status.MoveActive:
            self.clear_error(axis)
            fault = self.raw_write_read(self._cmd("AXISFAULT", axis))
            axis_fault = AerotechStatus(int(fault), self.AXIS_FAULT_BITS)

        return (axis_fault, axis_status)

    def state(self, axis):
        state = self._aero_state.new()

        (aero_fault, aero_status) = self.read_status(axis)

        if aero_fault.PositiveHardLimit or aero_fault.PositiveSoftLimit:
            state.set("LIMPOS")
        if aero_fault.NegativeHardLimit or aero_fault.NegativeSoftLimit:
            state.set("LIMNEG")
        if aero_status.HomeLimit:
            state.set("HOME")
        if aero_status.EmergencyStop:
            state.set("EXTSTOP")
        if aero_fault.ExternalInput:
            state.set("EXTDISABLE")
        if aero_status.Homed:
            state.set("HOMEDONE")

        if aero_fault.get() > 0:
            state.set("FAULT")
        else:
            if aero_status.Enabled:
                if aero_status.MoveActive or aero_status.Homing:
                    state.set("MOVING")
                else:
                    state.set("READY")
            else:
                state.set("OFF")

        if not state.MOVING:
            self._is_moving[axis.name] = False

        return state

    def __info__(self):
        version = self.raw_write_read("VERSION")
        comminfo = self._comm.__info__()
        return f"AEROTECH CONTROLLER:\n    version: {version}\n    {comminfo}"

    def get_id(self, axis):
        version = self.raw_write_read("VERSION")
        return "Aerotech axis %s - version %s" % (self._aero_name(axis), version)

    @object_method(types_info=("None", "str"))
    def get_info(self, axis):
        idstr = self.get_id(axis)
        (fault, status) = self.read_status(axis)
        info = "%s\n\nAxis Status : 0x%08x\n%s\n\nAxis Fault : 0x%08x\n%s\n" % (
            idstr,
            status.get(),
            str(status),
            fault.get(),
            str(fault),
        )
        return info

    def set_on(self, axis):
        self.raw_write(self._cmd_no_reply("ENABLE", axis))

    def set_off(self, axis):
        self.raw_write(self._cmd_no_reply("DISABLE", axis))

    def start_all(self, *motion_list):
        moves = []
        speeds = []

        for motion in motion_list:
            axis = motion.axis
            pos = motion.target_pos / axis.steps_per_unit
            aero_name = self._aero_name(axis)
            speed = self._aero_speed[axis.name]

            moves.append("%s %f" % ("D" if not aero_name else aero_name, pos))
            speeds.append("%sF %f" % (aero_name, speed))

        move_cmd = " ".join(moves)
        speed_cmd = " ".join(speeds)

        cmd = "MOVEABS %s %s" % (move_cmd, speed_cmd)
        self.raw_write(cmd)

        for motion in motion_list:
            self._is_moving[motion.axis.name] = True

    def start_jog(self, axis, velocity, direction):
        jog_vel = direction * velocity / abs(axis.steps_per_unit)
        cmd = self._cmd_no_reply("FREERUN", axis, jog_vel)
        self.raw_write(cmd)
        self._is_moving[axis.name] = True

    def stop_jog(self, axis):
        cmd = self._cmd_no_reply("FREERUN", axis, 0)
        self.raw_write(cmd)

    def read_position(self, axis):
        with self._lock:
            is_moving = self._is_moving.get(axis.name, False)
            if not is_moving:
                cmd = self._cmd("CMDPOS", axis)
            else:
                cmd = self._cmd("PFBK", axis)
            try:
                reply = self.raw_write_read(cmd)
            except SocketTimeout:
                log_info(self, "Retry on read_position SocketTimeout on ", axis.name)
                self._comm.flush()
                reply = self.raw_write_read(cmd)

            pos = float(reply) * axis.steps_per_unit
            return pos

    def set_velocity(self, axis, new_vel):
        self._aero_speed[axis.name] = new_vel / abs(axis.steps_per_unit)

    def read_velocity(self, axis):
        speed = self._aero_speed[axis.name] * abs(axis.steps_per_unit)
        return speed

    def read_acceleration(self, axis):
        acc = self._aero_acc[axis.name] * abs(axis.steps_per_unit)
        return acc

    def set_acceleration(self, axis, new_acc):
        acc = new_acc / abs(axis.steps_per_unit)
        self.raw_write(self._cmd_no_reply("RAMP RATE", axis, acc))
        self._aero_acc[axis.name] = acc

    def stop_all(self, *motion_list):
        axis_names = []
        for motion in motion_list:
            axis_names.append(self._aero_name(motion.axis))
        cmd = "ABORT " + " ".join(axis_names)
        self.raw_write(cmd)

    def home_search(self, axis, switch):
        # set home direction using HomeSetup Parameter
        home_dir = (switch > 0) and 0 or 1
        self.set_param(axis, "HomeSetup", home_dir)

        # TODO: fix implementation => wait will be done until 'home_state' returns good value,
        # there should be no loop here
        # start homing and wait for reply
        cmd = self._cmd_no_reply("HOME", axis)
        log_debug_data(self, "SEND", cmd)
        send_cmd = cmd + self.CMD_TERM
        with self._comm.lock:
            self._comm.write(send_cmd.encode())

            homing = True
            while homing:
                try:
                    reply = self._comm.read(size=1, timeout=1.0)
                    reply = reply.decode()
                    log_debug_data(self, "GET", reply)
                except:
                    reply = None

                if reply is not None:
                    if self._check_reply_code(reply, cmd):
                        homing = False
                else:
                    gevent.sleep(0.25)

    def home_state(self, axis):
        return AxisState("READY")

    def initialize_encoder(self, encoder):
        if encoder.name not in self._aero_enc.keys():
            aero_name = encoder.config.get("aero_name", str, None)
            if aero_name is None:
                raise ValueError(
                    "Missing aero_name key in %s encoder config" % encoder.name
                )
            self._aero_enc[encoder.name] = aero_name
            enc_axis = self._axis_from_aeroname(aero_name)
            output_divider = encoder.config.get("output_divider", int, None)
            if output_divider is not None:
                self.set_encoder_output_divider(enc_axis, output_divider)
            internal_divider = encoder.config.get("internal_divider", int, None)
            if internal_divider is not None:
                self.set_encoder_internal_divider(enc_axis, internal_divider)

    def _aero_encoder_axis(self, encoder):
        aero_enc = self._aero_enc.get(encoder.name, None)
        if aero_enc is None:
            raise ValueError("Aerotech Encoder [%s] not initialised" % encoder.name)
        return aero_enc

    def read_encoder(self, encoder):
        reply = self.raw_write_read("PFBK(%s)" % self._aero_encoder_axis(encoder))
        return float(reply)

    def get_encoder_steps_per_unit(self, encoder):
        aero_name = self._aero_encoder_axis(encoder)
        axis = self._axis_from_aeroname(aero_name)
        return self.get_encoder_output_resolution(axis)

    @object_method(types_info=("None", "int"))
    def get_encoder_internal_divider(self, axis):
        value = int(self.get_param(axis, "EmulatedQuadratureDivider"))
        self._internal_divider[axis.name] = value
        return value

    @object_method(types_info=("int", "None"))
    def set_encoder_internal_divider(self, axis, divider):
        value = int(divider)
        if value <= 1:
            raise ValueError("Aerotech Encoder Divider musst be > 1")
        self.set_param(axis, "EmulatedQuadratureDivider", divider)
        setdiv = self.get_encoder_internal_divider(axis)

    @object_method(types_info=("None", "int"))
    def get_encoder_output_divider(self, axis):
        value = int(self.get_param(axis, "EncoderDivider"))
        self._output_divider[axis.name] = value
        return value

    @object_method(types_info=("int", "None"))
    def set_encoder_output_divider(self, axis, divider):
        value = int(divider)
        if value < 0:
            raise ValueError("Aerotech Encoder Divider musst be > 0")
        self.set_param(axis, "EncoderDivider", divider)
        setdiv = self.get_encoder_output_divider(axis)

    @object_method(types_info=("None", "int"))
    def get_encoder_output_resolution(self, axis):
        return (
            axis.steps_per_unit
            / self._internal_divider[axis.name]
            / self._output_divider[axis.name]
        )

    def start_output_pulse(self, axis, start_pos, stop_pos, npoints):
        name = self._aero_name(axis)
        value = self.get_param(axis, "CountsPerUnit")
        enc_units = float(value)

        start_enc = int(start_pos * enc_units + 0.5)
        stop_enc = int(stop_pos * enc_units + 0.5)
        step_pos = (stop_pos - start_pos) / npoints
        step_enc = int(step_pos * enc_units + 0.5)

        # --- reset previous control
        self.raw_write(self._cmd_no_reply("PSOCONTROL", axis, "RESET"))

        # --- define mask window
        self.raw_write(self._cmd_no_reply("PSOWINDOW", axis, 1, "INPUT 1"))
        self.raw_write(
            self._cmd_no_reply(
                "PSOWINDOW", axis, 1, "RANGE %d, %d" % (start_enc, stop_enc)
            )
        )

        # --- define pulse 10usec up
        self.raw_write(self._cmd_no_reply("PSOPULSE", axis, "TIME 10,10"))

        # --- define distance tracking
        self.raw_write(self._cmd_no_reply("PSOTRACK", axis, "INPUT 1"))
        self.raw_write(self._cmd_no_reply("PSOTRACK", axis, "RESET %d" % 0x40))
        self.raw_write(self._cmd_no_reply("PSODISTANCE", axis, "FIXED %d" % step_enc))

        # --- activate output mode
        self.raw_write(
            self._cmd_no_reply("PSOOUTPUT", axis, "PULSE WINDOW MASK EDGE 2")
        )
        self.raw_write(self._cmd_no_reply("PSOCONTROL", axis, "ARM"))

    def stop_output_pulse(self, axis):
        self.raw_write(self._cmd_no_reply("PSOCONTROL", axis, "OFF"))

    @object_method(types_info=("str", "str"))
    def get_param(self, axis, name):
        try:
            param = AerotechParameter[name]
        except KeyError:
            raise ValueError("Unknown aerotech parameter [%s]" % name)
        cmd = self._cmd("GETPARM", axis, param.value)
        return self.raw_write_read(cmd)

    @object_method(types_info=(("str", "float"), "None"))
    def set_param(self, axis, name, value):
        try:
            param = AerotechParameter[name]
        except KeyError:
            raise ValueError("Unknown aerotech parameter [%s]" % name)
        else:
            param = param.value

        cmd = self._cmd("SETPARM", axis, param, value)
        self.raw_write(cmd)

    @object_method(types_info=("str", "list"))
    def get_param_list(self, axis, search_string=None):
        if search_string is not None and len(search_string) != 0:
            search_lower = search_string.lower()
            names = [
                par.name
                for idx, par in enumerate(AerotechParameter)
                if search_lower in par.name.lower()
            ]
        else:
            names = [par.name for idx, par in enumerate(AerotechParameter)]
        return names

    @object_method(types_info=("str", "str"))
    def dump_param(self, axis, name_start=None):
        partxt = "Aerotech axis %s parameters:\n" % self._aero_name(axis)
        for idx, par in enumerate(AerotechParameter):
            if name_start is None or par.name.startswith(name_start):
                value = self.get_param(axis, par.value)
                partxt += "%30s [%d] = %s\n" % (par.name, par.value, value)

        return partxt


class AerotechEncoder(Encoder):
    @property
    @lazy_init
    def steps_per_unit(self):
        return self.controller.get_encoder_steps_per_unit(self)

    @lazy_init
    def read(self):
        return self.controller.read_encoder(self)
