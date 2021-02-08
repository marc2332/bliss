#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import numpy as np
import io
import socket
import struct

HEADER_FORMAT = ">BBBBL"
DATA_FLAG = 0x80


class Lecroy620zi(object):
    """
    Define the methods used with the Lecroy scope Wave Runner 620Zi.
    """

    def __init__(self, host, port=1861, timeout=5.0):
        self._comm = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._comm.connect((host, port))
        self._comm.settimeout(timeout)

    def send(self, msg):
        if not msg.endswith("\n"):
            msg += "\n"
        msg = msg.encode()
        header = struct.pack(HEADER_FORMAT, 129, 1, 1, 0, len(msg))
        self._comm.sendall(b"".join([header, msg]))

    def recv(self, decode=True):
        dtstr = []
        while True:
            data = self._comm.recv(8)
            head_data = struct.unpack("B3BI", data)  # get response (header from device)
            lnt = socket.ntohl(head_data[-1])  # data length to be captured
            flg = head_data[0]
            dtstr.append(self._comm.recv(lnt))
            if flg != DATA_FLAG:  # data flag 0x80
                break
        answr = b"".join(dtstr)
        if decode:
            answr = answr.decode()
            if answr.endswith("\n"):
                answr = answr[:-1]
        return answr

    def rst(self):
        """Initiate a device reset."""
        self.send("*RST")

    def rcl(self):
        """Recalls one of five non-volatile panel setups."""
        self.send("*RCL")

    def clsw(self):
        """Restarts the cummulative processing functions."""
        self.send("CLSW")

    def wait(self):
        """Prevents new analysis until current is completd."""
        self.send("WAIT")

    def trg(self):
        """Executes an ARM command."""
        self.send("*TRG")

    def get_trmd(self):
        """
        Read the trigger mode.
        """
        self.send("TRMD?")
        return self.recv()

    def set_trmd(self, cmd):
        """
        Specifies the trigger mode.
        Example: set_trmd({"AUTO","NORM","STOP"})
        """
        self.send("TRMD " + cmd)

    def get_trlv(self):
        """Adjusts the trigger level of the specified trigger source."""
        self.send("TRLV?")
        return self.recv()

    def get_trcp(self):
        """Sets the coupling mode of the specified trigger source."""
        self.send("TRCP?")
        return self.recv()

    def set_trdl(self, val):
        """Sets the time delay at which the trigger occurs."""
        val = str(val)
        self.send("TRDL " + val)

    def get_trdl(self):
        """Read the time delay at which the trigger is to occur."""
        self.send("TRDL?")
        return self.recv()

    def get_trpa(self):
        """Sets the time at which the trigger is to occur."""
        self.send("TRPA?")
        return self.recv()

    def get_trsl(self):
        """Sets the time at which the trigger is to occur."""
        self.send("TRSL?")
        return self.recv()

    def set_tdiv(self, val):
        """
        Modifies the timebase setting.
        Example: set_tdiv(1e-6)
        """
        val = str(val)
        self.send("TDIV " + val)

    def get_tdiv(self):
        """Read the timebase setting."""
        msg = "TDIV?"
        self.send(msg)
        return self.recv()

    def set_vdiv(self, ch, val):
        """
        Sets the vertical sensitivity.
        Example: set_vdiv("C1",5)
        """
        val = str(val)
        self.send(ch + ":VDIV " + val)

    def get_vdiv(self, ch):
        """
        Read the vertical sensitivity.
        Example: get_vdiv("C1")
        """
        self.send(ch + ":VDIV?")
        return self.recv()

    def set_ofst(self, ch, val):
        """
        Allows output channel vertical offset adjustment.
        Example: set_ofst("C1",2)
        """
        val = str(val)
        self.send(ch + ":OFST " + val)

    def get_ofst(self, ch):
        """
        Read output channel vertical offset adjustment.
        Example: get_ofst("C1")
        """
        self.send(ch + ":OFST?")
        # print repr(self._comm.recv())
        return self.recv()

    def set_cpl(self, ch, cpl):
        """
        Selects the specified input channel's coupling mode.
        Example: set_cpl("C1",{"D[{1M,50}]","A[{1M,50}]","GND"})
        """
        cpl = str(cpl)
        lenCpl = len(cpl)

        if lenCpl == 1:
            self.send(ch + ":CPL " + cpl + "1M")
        elif lenCpl == 3:
            self.send(ch + ":CPL " + cpl)

        self.send(ch + ":CPL?")
        # print repr(self._comm.recv())

    def get_cpl(self, ch):
        """
        Read the specified input channel's coupling mode.
        Example: get_cpl("C1")
        """
        self.send(ch + ":CPL?")
        # print repr(self._comm.recv())
        return self.recv()

    def set_waveformFormat(self, dataFormat):
        """
        Selects the format the oscilloscope uses to send waveform data. Cord is fixed to \"LOW\".
        Example: set_waveformFormat({"WORD","BYTE"})
        """
        self.send("CFMT DEF9," + dataFormat + ",BIN")
        self.send("CORD LO")

    def get_waveformFormat(self):
        """
        Read the selected format (CFMT, CORD) used by the oscilloscope to send waveform data.
        """
        self.send("CFMT?")
        cfmt = self.recv()
        self.send("CORD?")
        cord = self.recv()
        return cfmt, cord

    def set_waveformSetup(self, sp=256, np=0, fp=0, sn=0):
        """
        Selected the amount of data in a waveform to be transmitted (WFSU).
        Default: sp=256,np=0,fp=0,sn=0
        """
        sp = str(sp)
        np = str(np)
        fp = str(fp)
        sn = str(sn)
        self.send("WFSU SP," + sp + ",NP," + np + ",FP," + fp + ",SN," + sn)

    def get_waveformSetup(self):
        """
        Selected the amount of data in a waveform to be transmitted (WFSU).
        Default: sp=0,np=0,fp=0,sn=0
        """
        self.send("WFSU?")
        # string values
        result = self.recv()
        # int values
        return result
        return map(int, result.split(",")[1::2])

    def get_inr(self):
        """
        Return the INR status.
        """
        self.send("INR?")
        inr = self.recv()
        inr = inr[3:]
        inr = int(inr)
        return inr

    def get_opc(self):
        """
        Return the INR status.
        """
        self.send("*OPC?")
        opc = self.recv()
        opc = opc[4:]
        opc = int(opc)
        return opc

    def set_memory_size(self, val):
        """
        Modifies the memory size setting.
        Example: set_memory_size(1e3)
        """
        val = str(val)
        self.send("MEMORY_SIZE " + val)

    def get_memory_size(self):
        """Read the memory size setting."""
        self.send("MEMORY_SIZE?")
        ans = self.recv()
        return ans
        a, value, c = ans.split(" ")
        value = float(value)
        return value

    def set_math_setup_sweeps(self, args):
        """
        Set for the mathematical function selected with the number of sweeps.
        Example: set_math_setup_sweeps("F1", "128")
        """
        mathChan = args[0]
        Sweeps = args[1]
        command = "VBS app.Math." + mathChan + ".Operator1Setup.Sweeps=" + Sweeps
        self.send(command)

    def get_math_setup_sweeps(self, mathChan):
        """
        Read the number of sweeps for the selected mathematical function.
        Example: get_math_setup_sweeps("F1")
        """
        command = "VBS? RETURN=app.Math." + mathChan + ".Operator1Setup.Sweeps"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def get_math_out_sweeps(self, mathChan):
        """
        Read the number of executed sweeps for the selected mathematical function.
        Example: get_math_out_sweeps("F1")
        """
        command = "VBS? RETURN=app.Math." + mathChan + ".Out.Result.Sweeps"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def set_smart_memory(self, memoryMode):
        """
        Sets the mode of memory management to one of the two modes:

        SetMaximumMemory – Maximizes the memory length for the given timebase setting; limited by the
        maximum length that is compatible with the maximum sampling rate that the DSO can achieve.

        FixedSampleRate – Keeps the sampling rate the same when the timebase is changed; limited by the
        maximum sampling rate that the DSO can achieve.
        Example: set_smart_memory("SetMaximumMemory")
        or set_smart_memory("FixedSampleRate")
        """
        command = (
            "VBS app.Acquisition.Horizontal.SmartMemory = " + '"' + memoryMode + '"'
        )
        self.send(command)

    def get_smart_memory(self):
        """
        Read the mode of memory management.
        """
        command = "VBS? RETURN=app.Acquisition.Horizontal.SmartMemory"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def set_sample_rate(self, sampleRate):
        """
        Queries the sample rate of the ADCs.
        If random interleaved sampling (RIS) is in use, this value will be
        less than the effective sampling rate of the traces.

        Range: From 500 to 1e+010, step 1e+008, locked to 1 2.5 5

        Example: set_sample_rate(2e6)
        """
        sampleRate = str(sampleRate)
        command = (
            "VBS app.Acquisition.Horizontal.SampleRate = " + '"' + sampleRate + '"'
        )
        self.send(command)

    def get_sample_rate(self):
        """
        Queries the sample rate of the ADCs.
        If random interleaved sampling (RIS) is in use, this value will be
        less than the effective sampling rate of the traces.
        """
        command = "VBS? RETURN=app.Acquisition.Horizontal.SampleRate"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        value = int(value)
        return value

    def get_math_measure_control_reference(self, MathMeaschan):
        """
        Read the math/measure controle reference..
        Example: get_math_measure_control_reference("F1") returns, Average, Histrogram, etc.
        """
        command = "VBS? RETURN=app.Math." + MathMeaschan + ".Operator1"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def get_math_histogram_setup_value(self, mathChan):
        """
        Read the mathematical histogram value.
        Example: get_math_histogram_value("F1") returns an integer like 2000.
        """
        command = "VBS? RETURN=app.Math." + mathChan + ".Operator1Setup.Values"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def get_math_histogram_population_inside(self, mathChan):
        """
        Read the number of population histogram in the buffer.
        Example: get_math_out_sweeps("F4") returns an integer like 2000.
        """
        command = "VBS? RETURN=app.Math." + mathChan + ".Out.Result.PopulationInside"
        self.send(command)
        ans = self.recv()
        a, value = ans.split(" ")
        return value

    def format_waveform(self, recvd, ch):
        all = []
        all.append(recvd)
        all = b"".join(all)
        if all.endswith(b"\n"):
            all = all[:-1]
        waveStart = 21
        waveDescLength = int(all[18:21])
        arrayAll = np.fromstring(all[waveDescLength + waveStart :], dtype=np.int16)
        # data in the array
        # self.arrayListChannel[ch]= arrayAll
        # self.dArrayData[ch] = arrayAll

        CHANNEL = ch
        wavedescAll = struct.unpack(
            "<16s16shhiiiiiiiiii16si16shhiiiiiiiiihhffffhhfdd48s48sf16sfHHhhHHfHHffH",
            all[waveStart : waveStart + 346],
        )
        descriptor_name = wavedescAll[0].replace(b"\x00", b"")
        template_name = wavedescAll[1].replace(b"\x00", b"")
        dComm_type = {"0": "BYTE", "1": "WORD"}
        COMM_TYPE = dComm_type.get(str(wavedescAll[2]))
        dComm_order = {"0": "HIFIRST", "1": "LOFIRST"}
        COMM_ORDER = dComm_order.get(str(wavedescAll[3]))
        WAVE_DESCRIPTOR = str(wavedescAll[4])
        WAVE_ARRAY_1 = str(wavedescAll[10])
        INSTRUMENT_NAME = wavedescAll[14].replace(b"\x00", b"")
        INSTRUMENT_NUMBER = str(wavedescAll[15])
        # WAVE_ARRAY_COUNT is not wavedescAll[19]
        # because the 3 fist points are bad
        arrayAllSize = len(arrayAll)
        WAVE_ARRAY_COUNT = str(arrayAllSize)
        PNTS_PER_SCREEN = str(wavedescAll[20])
        FIRST_VALID_PNT = str(wavedescAll[21])
        LAST_VALID_PNT = str(wavedescAll[22])
        FIRST_POINT = str(wavedescAll[23])
        SPARSING_FACTOR = str(wavedescAll[24])
        SEGMENT_INDEX = str(wavedescAll[25])
        SUBARRAY_COUNT = str(wavedescAll[26])
        SWEEPS_PER_ACQ = str(wavedescAll[27])
        POINTS_PER_PAIR = str(wavedescAll[28])
        PAIR_OFFSET = str(wavedescAll[29])
        VERTICAL_GAIN = str(wavedescAll[30])
        VERTICAL_OFFSET = str(wavedescAll[31])
        MAX_VALUE = str(wavedescAll[32])
        MIN_VALUE = str(wavedescAll[33])
        NOMINAL_BITS = str(wavedescAll[34])
        NOM_SUBARRAY_COUNT = str(wavedescAll[35])
        HORIZ_INTERVAL = str(wavedescAll[36])
        HORIZ_OFFSET = str(wavedescAll[37])
        PIXEL_OFFSET = str(wavedescAll[38])
        VERTUNIT = wavedescAll[39].replace(b"\x00", b"")
        HORUNIT = wavedescAll[40].replace(b"\x00", b"")
        HORIZ_UNCERTAINTY = str(wavedescAll[41])
        TRIGGER_TIME = struct.unpack("dbbbbhh", wavedescAll[42])  # time_stamp
        s = str(TRIGGER_TIME[0])
        min = str(TRIGGER_TIME[1])
        h = str(TRIGGER_TIME[2])
        dd = str(TRIGGER_TIME[3])
        mm = str(TRIGGER_TIME[4])
        yyyy = str(TRIGGER_TIME[5])
        ACQ_DURATION = str(wavedescAll[43])
        dRecord_type = {
            "0": "single_sweep",
            "1": "interleaved",
            "2": "histogram",
            "3": "graph",
            "4": "filter_coefficient",
            "5": "complex",
            "6": "extrema",
            "7": "sequence_obsolete",
            "8": "centered_RIS",
            "9": "peak_detect",
        }
        RECORD_TYPE = dRecord_type.get(str(wavedescAll[44]))
        dPocessing_done = {
            "0": "no_processing",
            "1": "fir_filter",
            "2": "interpolated",
            "3": "sparsed",
            "4": "auto_scaled",
            "5": "no_result",
            "6": "rolling",
            "7": "cumulative",
        }
        PROCESSING_DONE = dPocessing_done.get(str(wavedescAll[45]))
        dTime_base = {
            "0": "1_ps/div",
            "1": "2_ps/div",
            "2": "5_ps/div",
            "3": "10_ps/div",
            "4": "20_ps/div",
            "5": "50_ps/div",
            "6": "100_ps/div",
            "7": "200_ps/div",
            "8": "500_ps/div",
            "9": "1_ns/div",
            "10": "2_ns/div",
            "11": "5_ns/div",
            "12": "10_ns/div",
            "13": "20_ns/div",
            "14": "50_ns/div",
            "15": "100_ns/div",
            "16": "200_ns/div",
            "17": "500_ns/div",
            "18": "1_us/div",
            "19": "2_us/div",
            "20": "5_us/div",
            "21": "10_us/div",
            "22": "20_us/div",
            "23": "50_us/div",
            "24": "100_us/div",
            "25": "200_us/div",
            "26": "500_us/div",
            "27": "1_ms/div",
            "28": "2_ms/div",
            "29": "5_ms/div",
            "30": "10_ms/div",
            "31": "20_ms/div",
            "32": "50_ms/div",
            "33": "100_ms/div",
            "34": "200_ms/div",
            "35": "500_ms/div",
            "36": "1_s/div",
            "37": "2_s/div",
            "38": "5_s/div",
            "39": "10_s/div",
            "40": "20_s/div",
            "41": "50_s/div",
            "42": "100_s/div",
            "43": "200_s/div",
            "44": "500_s/div",
            "45": "1_ks/div",
            "46": "2_ks/div",
            "47": "5_ks/div",
            "100": "EXTERNAL",
        }
        TIME_BASE = dTime_base.get(str(wavedescAll[48]))
        dVert_coupling = {
            "0": "DC_50_Ohm",
            "1": "ground",
            "2": "DC_1MOhm",
            "3": "ground",
            "4": "AC_1MOhm",
        }
        VERT_COUPLING = dVert_coupling.get(str(wavedescAll[49]))
        PROBE_ATT = str(wavedescAll[50])
        dFixed_vert_gain = {
            "0": "1_uv/div",
            "1": "2_uv/div",
            "2": "5_uv/div",
            "3": "10_uv/div",
            "4": "20_uv/div",
            "5": "50_uV/div",
            "6": "100_uV/div",
            "7": "200_uV/div",
            "8": "500_uV/div",
            "9": "1_mV/div",
            "10": "2_mV/div",
            "11": "5_mV/div",
            "12": "10_mV/div",
            "13": "20_mV/div",
            "14": "50_mV/div",
            "15": "100_mV/div",
            "16": "200_mV/div",
            "17": "500_mV/div",
            "18": "1_V/div",
            "19": "2_V/div",
            "20": "5_V/div",
            "21": "10_V/div",
            "22": "20_V/div",
            "23": "50_V/div",
            "24": "100_V/div",
            "25": "200_V/div",
            "26": "500_V/div",
            "27": "1_kV/div",
        }
        FIXED_VERT_GAIN = dFixed_vert_gain.get(str(wavedescAll[51]))
        BANDWIDTH_LIMIT = str(wavedescAll[52])
        dBandwidth_limit = {"0": "off", "1": "on"}
        BANDWIDTH_LIMIT = dBandwidth_limit.get(str(wavedescAll[52]))
        VERTICAL_VERNIER = str(wavedescAll[53])
        ACQ_VERT_VERNIER = str(wavedescAll[54])
        # dWave_source = {'0':'CHANNEL_1', '1':'CHANNEL_2', '2':'CHANNEL_3', '3':'CHANNEL_4', '9':'UNKNOWN',
        # 'NONE':'UNKNOWN'}
        # WAVE_SOURCE  = dWave_source.get(str(wavedescAll[55]))
        WAVE_SOURCE = ch
        # print("WAVE_SOURCE parameter = {0}".format(wavedescAll[55]))

        # ===== Header =====
        f = io.StringIO()
        f.write("==== CHANNEL PARAMETERS: " + ch + " ====\n")
        f.write("DESCRIPTOR_NAME : " + descriptor_name.decode() + "\n")
        f.write("TEMPLATE_NAME : " + template_name.decode() + "\n")
        f.write("COMM_TYPE : " + COMM_TYPE + "\n")
        f.write("COMM_ORDER : " + COMM_ORDER + "\n")
        f.write("WAVE_DESCRIPTOR : " + WAVE_DESCRIPTOR + "\n")
        f.write("WAVE_ARRAY_1 : " + WAVE_ARRAY_1 + "\n")
        f.write("INSTRUMENT_NAME : " + INSTRUMENT_NAME.decode() + "\n")
        f.write("INSTRUMENT_NUMBER : " + INSTRUMENT_NUMBER + "\n")
        f.write("WAVE_ARRAY_COUNT : = " + WAVE_ARRAY_COUNT + "\n")
        f.write("PNTS_PER_SCREEN : " + PNTS_PER_SCREEN + "\n")
        f.write("FIRST_VALID_PNT : " + FIRST_VALID_PNT + "\n")
        f.write("LAST_VALID_PNT : " + LAST_VALID_PNT + "\n")
        f.write("FIRST_POINT : " + FIRST_POINT + "\n")
        f.write("SPARSING_FACTOR : " + SPARSING_FACTOR + "\n")
        f.write("SEGMENT_INDEX : " + SEGMENT_INDEX + "\n")
        f.write("SUBARRAY_COUNT : " + SUBARRAY_COUNT + "\n")
        f.write("SWEEPS_PER_ACQ : " + SWEEPS_PER_ACQ + "\n")
        f.write("POINTS_PER_PAIR : " + POINTS_PER_PAIR + "\n")
        f.write("PAIR_OFFSET : " + PAIR_OFFSET + "\n")
        f.write("VERTICAL_GAIN : " + VERTICAL_GAIN + "\n")
        f.write("VERTICAL_OFFSET : " + VERTICAL_OFFSET + "\n")
        f.write("MAX_VALUE : " + MAX_VALUE + "\n")
        f.write("MIN_VALUE : " + MIN_VALUE + "\n")
        f.write("NOMINAL_BITS : " + NOMINAL_BITS + "\n")
        f.write("NOM_SUBARRAY_COUNT : " + NOM_SUBARRAY_COUNT + "\n")
        f.write("HORIZ_INTERVAL : " + HORIZ_INTERVAL + "\n")
        f.write("HORIZ_OFFSET : " + HORIZ_OFFSET + "\n")
        f.write("PIXEL_OFFSET : " + PIXEL_OFFSET + "\n")
        f.write("VERTUNIT : " + VERTUNIT.decode() + "\n")
        f.write("HORUNIT : " + HORUNIT.decode() + "\n")
        f.write("HORIZ_UNCERTAINTY : " + HORIZ_UNCERTAINTY + "\n")
        f.write(
            "TRIGGER_TIME : date = "
            + yyyy
            + "-"
            + mm
            + "-"
            + dd
            + ", time = "
            + h
            + ":"
            + min
            + ":"
            + s
            + "\n"
        )
        f.write("ACQ_DURATION : " + ACQ_DURATION + "\n")
        f.write("RECORD_TYPE : " + RECORD_TYPE + "\n")
        f.write("PROCESSING_DONE : " + PROCESSING_DONE + "\n")
        f.write("TIME_BASE : " + TIME_BASE + "\n")
        f.write("VERT_COUPLING : " + VERT_COUPLING + "\n")
        f.write("PROBE_ATT : " + PROBE_ATT + "\n")
        f.write("FIXED_VERT_GAIN : " + FIXED_VERT_GAIN + "\n")
        f.write("BANDWIDTH_LIMIT : " + BANDWIDTH_LIMIT + "\n")
        f.write("VERTICAL_VERNIER : " + VERTICAL_VERNIER + "\n")
        f.write("ACQ_VERT_VERNIER : " + ACQ_VERT_VERNIER + "\n")
        f.write("WAVE_SOURCE : " + WAVE_SOURCE + "\n")
        f.write("\n")
        # np.savetxt(f,arrayAll,fmt='%i')

        return f.getvalue(), arrayAllSize, arrayAll

    def ask_waveform(self, ch):
        tdiv = float(self.get_tdiv().split()[1])
        cptr_time = tdiv * 10 + 1
        self.send(ch + ":WF? ALL")
        time.sleep(cptr_time)

    def answer_waveform(self, ch):
        recvd = self.recv(False)
        return self.format_waveform(recvd, ch)

    def get_waveform(self, ch):
        """
        Transfers a waveform data with the selected format according to CFMT, CORD and WFSU.
        Returns the scope parameters and the data waveform in a string.
        Example: get_waveform("C1")
        """

        self.ask_waveform(ch)
        return self.answer_waveform(ch)
