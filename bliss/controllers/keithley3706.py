# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Keithley K3706 multimeter.

# to initialize:
# in the code:
#   change all nplc to 5  (3 places)
#   and change slot_ in read_all()
#
# in a session:
# k37dcm.send_prog_dmm()
#
# then relaunch thesession  ???

"""

import time
import math
from blessings import Terminal
from pt100 import lookuptable

from bliss.comm.util import get_comm, TCP
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.logtools import log_debug, user_print
from bliss import global_map


t = Terminal()


"""
k37dcm.send("reset()")
k37dcm.send("errorqueue.clear()")
k37dcm.send("channel.setpole(\"slot4\", 4)")
k37dcm.send("dmm.close(\"4001,4002,4003,4004,4005\")")   # <<<< string too long.
k37dcm.send("")
"""

"""
slot 4 config:
# R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
# R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
# R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
# R100_4W_conf,R100_4W_conf,nofunction,nofunction
# 21 22  : nofunction
"""


k37dcm_prog_dmm = """beeper.beep(0.2,2400)
reset()
# configure the device
dmm.func=\"fourwireohms\"
dmm.aperture=0.02
dmm.linesync=dmm.OFF
dmm.autorange=dmm.OFF
dmm.range=100
dmm.nplc=5
dmm.autodelay=0
dmm.autozero=0
# dmm.close(\"4011,4922\")
format.asciiprecision = 7
# saves config as R100_4W_conf
dmm.configure.set(\"R100_4W_conf\")
# apply this config to All full slots.
dmm.setconfig(\"slot1\",\"R100_4W_conf\")
dmm.setconfig(\"slot2\",\"R100_4W_conf\")
dmm.setconfig(\"slot3\",\"R100_4W_conf\")
dmm.setconfig(\"slot4\",\"R100_4W_conf\")
"""

k37dcm_prog_slot = """
bufM{0}=dmm.makebuffer({1})
bufM{0}.clear()
bufM{0}.appendmode=1
scan.create(\"{2}\")
scan.scancount={3}
scan.background(bufM{0})
"""

# scan.background(bufM{0})   <--- start the scan


"""
ERRORS:
   1114  interlock : check connectors

"""


"""
###############  BUFFER

bufM1=dmm.makebuffer(200)
To delete a buffer, set bufM1 to nil.

k37dcm.read("print(bufM1.capacity)")   #  overall buffer size.

k37dcm.read("print(bufM1.n)")  # number of readings currently stored in the buffer.
bufferVar.collecttimestamps = 1 (ON) or 0 (OFF); default is 1.

To see timestamps that are in buffer:
 bufferVar.collecttimestamps = 1
 print(x, y, bufM1, bufM1.timestamps)

k37dcm.send("bufM1.collecttimestamps = 1") # Cannot change this setting unless buffer is cleared
k37dcm.read("print(1, 2, bufM1, bufM1.timestamps)")

k37dcm.send("maxcapa=dmm.buffer.maxcapacity")
print k37dcm.read("print(maxcapa)")
6.500000000e+05  #  650 000
"""

# scan.execute(bufM1)  # !!! cannot do state() with execute => use background()
# scan.scancount=100   # number of times the scan is repeated
# dmm.close(\"4001,4002,4003,4004,4005\")"   #  !!! ERR : string too long.

# delay(0.5) # needed ?
# dmm.nplc=5  # !!! duration : ?  (5s for 0.1????)

# dmm.close("4001,4002,4003,4004") # !!! ERR : (1115, 'Parameter error no multiple specifiers accepted')

# dmm.func  : selects the active measure function.
#   "accurrent" or dmm.AC_CURRENT
#   "acvolts" or dmm.AC_VOLTS
#   "commonsideohms" or dmm.COMMON_SIDE_OHMS
#   "continuity" or dmm.CONTINUITY
#   "dccurrent" or dmm.DC_CURRENT
#   "dcvolts" or dmm.DC_VOLTS
#   "fourwireohms" or dmm.FOUR_WIRE_OHMS
#   "frequency" or dmm.FREQUENCY
#   "nofunction" or dmm.NO_FUNCTION
#   "period" or dmm.PERIOD
#   "temperature" or dmm.TEMPERATURE
#   "twowireohms" or dmm.TWO_WIRE_OHMS

# dmm.close("4001") # !!! ERR NB: (1114, 'Settings conflict with nofunction as DMM function')
#   If error code 1114, "Settings conflict error," is displayed, the
#   channel that is being closed has "nofunction" assigned to it. For
#   remote operation, to use dmm.close, you must assign a valid function
#   to a channel.


class K37Counter(SamplingCounter):
    def __init__(self, name, controller, slot, channel, unit=None):

        super().__init__(name, controller)
        #                      ref to the controller
        # the reading of many counters depending on the same
        # controller will be performed using  controller.read_all() function

        self.unit = unit
        self.slot = slot
        self.channel = channel
        self.id = 1000 * slot + channel


class Keithley3706(SamplingCounterController):
    """
    Keithly K3706 controller.
    """

    def __init__(self, name, config):

        super().__init__(name)

        self.bliss_config = config

        # Use "\n" as eol if not specified in config.
        try:
            self.msg_eol = config.get("tcp")["eol"]
        except KeyError:
            self.msg_eol = "\n"

        # eol used by socket when reading lines.
        self.comm = get_comm(config, TCP, eol=self.msg_eol, port=5025)

        self.max_sampling_frequency = config.get("max_sampling_frequency", 1)

        for counter_conf in config.get("counters", list()):
            unit = counter_conf.get_inherited("unit")
            slot = counter_conf.get("slot")

            # counter in degree
            self.create_counter(
                K37Counter,
                counter_conf["counter_name"],
                slot=slot,
                channel=counter_conf["channel"],
                unit=unit,
            )

            # counter in ohms
            self.create_counter(
                K37Counter,
                counter_conf["counter_name"] + "_ohms",
                slot=slot,
                channel=counter_conf["channel"],
                unit=unit,
            )

        ###        # hummm beurk
        ###        self.slot_idx = slot
        ###        ######## -> to be improved !!! ???

        # self.chan_count = len(self.counters)
        self.chan_count = 18

        self.scancount = 1

        self._print_com = False

        self.values_ohms = {}
        self.values_degrees = {}

        log_debug(self, "Keithley3706 init")

        global_map.register(self, children_list=[self.comm])

        #  To be executed once after device reboot:
        # self.config_all_slots()

    def __info__(self):
        info_str = "KEITHLEY 3706\n"
        try:
            info_str += "ID: " + self.comm.write_readline(b"*IDN?\n").decode()
            info_str += "\n"
        except:
            info_str += "ERROR: cannot communicate with device\n"

        return info_str

    def read_all(self, *counters):

        # Fill self.values_ohms and self.values_degrees
        self.run_slot_reading(1)
        self.run_slot_reading(2)
        self.run_slot_reading(3)
        self.run_slot_reading(4)

        rlist = list()

        for counter in counters:
            try:
                # print "counter=", counter.slot, counter.channel
                if "_ohms" in counter.name:
                    rlist.append(self.values_ohms[counter.slot][counter.channel - 1])
                else:
                    rlist.append(self.values_degrees[counter.slot][counter.channel - 1])
            except:
                rlist.append(9999)
        return rlist

    def mytest(self, scan_nb_points=10):
        self.send("reset()")
        self.send("errorqueue.clear()")
        self.send("format.asciiprecision = 7")

        self.config_slot(1)
        self.config_slot(2)
        self.config_slot(3)
        self.config_slot(4)

        self.scancount = scan_nb_points

        # Sends pre defined DMM program
        self.send_prog_dmm()

        self.run_all_scans()

    def run_all_scans(self):
        """
        For tests
        """
        for slot_idx in range(4):
            self.run_scan(slot_idx + 1)

    def run_scan(self, slot_idx):
        """
        Run scan for slot <slot_idx> and read corresponding buffer.
        Return a list of floats.
        """
        log_debug(self, "run_scan(slot_idx=%s", slot_idx)
        self.send_prog_slot(slot_idx)

        log_debug(self, "wait start of scan")
        user_print(self.comm.write_readline(b"*IDN?\n", timeout=15).decode())
        log_debug(self, "scan started")

        scan_points_read = self.get_scan_states()[1]
        last_scan_index = 0

        while scan_points_read < 1:
            user_print("...")
            time.sleep(0.05)
            scan_points_read = self.get_scan_states()[1]

        while scan_points_read < self.scancount:
            time.sleep(0.5)

            buff_from = last_scan_index * self.chan_count + 1
            buff_to = scan_points_read * self.chan_count

            buff = self.read(f"printbuffer({buff_from},{buff_to},bufM{slot_idx})")

            user_print(list(map(float, buff.split(","))))

            last_scan_index = scan_points_read
            scan_points_read = self.get_scan_states()[1]

        # Read potential remaining points.
        if scan_points_read != self.scancount:
            user_print("ERROR : not all points read ??")
        else:
            buff_from = last_scan_index * self.chan_count + 1
            buff_to = scan_points_read * self.chan_count
            user_print(f"reading {buff_from}..{buff_to}")

            buff = self.read(f"printbuffer({buff_from},{buff_to},bufM{slot_idx})")

            user_print(list(map(float, buff.split(","))))

    def run_slot_reading(self, slot_idx):
        """
        Run scan for slot <slot_idx>
        Read correspondign buffer.
        fill self.values_degrees[slot_idx] with 18 buffer values
        """
        log_debug(self, "run_slot_reading(slot_idx=%s", slot_idx)

        self.send_prog_slot(slot_idx)

        log_debug(self, "wait start of scan")
        self.comm.write_readline(b"*IDN?\n", timeout=15).decode()
        log_debug(self, "scan started")

        # check state/number of points read.
        scan_points_read = self.get_scan_states()[1]

        while scan_points_read < self.scancount:
            time.sleep(0.05)
            user_print(".")
            scan_points_read = self.get_scan_states()[1]

        # Read all points.
        if scan_points_read != self.scancount:
            user_print("ERROR : not all points read ??")
        else:
            buff_from = 1
            buff_to = scan_points_read * self.chan_count

            buff = self.read(f"printbuffer({buff_from},{buff_to},bufM{slot_idx})")

            self.values_ohms[slot_idx] = list(map(float, buff.split(",")))
            self.values_degrees[slot_idx] = list(
                map(self.resistance_to_temperature, self.values_ohms[slot_idx])
            )

    #    def resistance_to_temperature(self, res_value):
    #        """
    #        Converts a resistance value in ohms into a temperature value in degrees.
    #        source: https://techoverflow.net/2016/01/02/accurate-calculation-of-pt100pt1000-temperature-from-resistance/
    #        """
    #         A = 3.9083e-3
    #         B = -5.7750e-7
    #         C = 0
    #         R0 = 100
    #         Rt = res_value
    #         a = ?
    #         b = ?
    #
    #         sqrterm = pow(R0 + a, 2)  - 4 * R0 * B * ( R0- Rt)
    #         num = -R0 * a + math.srqt(sqrterm)
    #         denum = 2 * R0 * b
    #
    #         temp = num / denum

    def resistance_to_temperature(self, resistor_value):
        """
        Converts a resistance value in ohms into a temperature value in degrees.
        Using python pt100 module.
        """
        """
        NB: little bench:
        BLISS [33]: timeit.timeit('import pt100;pt100.lookuptable.interp_resist_to_temp_naive(33)', number=100000)
        Out [33]: 0.6348822116851807

        BLISS [34]: timeit.timeit('import pt100;pt100.lookuptable.interp_resist_to_temp_np(33)', number=100000)
        Out [34]: 6.518273115158081
        """
        fval = lookuptable.interp_resist_to_temp_np(resistor_value)
        trunc_val = math.trunc(1000 * fval) / 1000.0  # trunc to milli-degree

        return trunc_val

    def print_com(self, state):
        self._print_com = state

    def send(self, message):
        """
        * Add terminator ("\n")
        * convert to bytes
        * Send <message> to the device.
        The write eol terminator is here the same used by socket to read lines.
        """
        if self._print_com:
            user_print(">>", message)
        self.comm.flush()
        _cmd = message + self.msg_eol
        _cmd_bytes = _cmd.encode()
        self.comm.write(_cmd_bytes)

        time.sleep(0.01)
        err = self.get_error()
        if err[0] != 0:
            user_print(" {t.red}ERROR:{t.normal}".format(t=t)),
            user_print(err)

    def get_error(self):
        self.comm.write(b"count = errorqueue.count" + self.msg_eol.encode())
        err = self.comm.write_readline(b"print(count)" + self.msg_eol.encode()).decode()
        err_count = int(float(err))
        errors = list()

        for err_idx in range(err_count):
            self.comm.write(
                b"errorcode, message = errorqueue.next()" + self.msg_eol.encode()
            )
            err_raw = self.comm.write_readline(
                b"print(errorcode, message)" + self.msg_eol.encode()
            ).decode()
            # err looks like :
            # "-2.86000e+02\tTSP Runtime error at line 1: attempt to index field `channel' (a nil value)"
            err_fields = err_raw.split("\t")
            errors.append((int(float(err_fields[0])), err_fields[1]))

        return (err_count, errors)

    def read(self, message):
        """
        * Add terminator
        * convert into bytes
        * send <message> to the device
        * convert answer into str return it.
        The write eol terminator is the same used by socket to read lines.
        Termination char is removed from answer by socket object.
        """
        if self._print_com:
            user_print(">>", message)
        self.comm.flush()  # ???
        _cmd = message + self.msg_eol
        _cmd_bytes = _cmd.encode()
        ans = self.comm.write_readline(_cmd_bytes).decode()
        # print "ans << %r" % ans
        return ans

    """ INFO """

    def get_id(self):
        """
        Returns identification string.
        Return value is like: 'KEITHLEY INSTRUMENTS INC.,MODEL 3706A,04349716,01.55a'
        """
        return self.read("*IDN?")

    def get_slot_config(self, slot_index):
        """
        dmm.getconfig() : queries for the DMM configurations that are
        associated with the specified channels or channel patterns.
        """
        self.send('slotConfig = dmm.getconfig("slot{}")'.format(slot_index))
        # Out [1]: 'R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
        #           R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
        #           R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,R100_4W_conf,
        #           R100_4W_conf,R100_4W_conf,R100_4W_conf,
        #           R100_4W_conf,R100_4W_conf,nofunction,nofunction'

        ans = self.read("print(slotConfig)")
        func_list = ans.split(",")
        return func_list

    def print_slot_config(self, slot_idx):
        ans = self.get_slot_config(slot_idx)
        for ii in range(len(ans)):
            user_print(f"{ii + 1}: {ans[ii]}")

    def send_prog_dmm(self):
        user_print("    --- SEND PROG DMM  --- ")

        for instruction in k37dcm_prog_dmm.split("\n"):
            if instruction.find("#") == -1:
                self.send(instruction)
            else:
                user_print(instruction)
        user_print("    --------------------    ")

    def send_prog_slot(self, slot_idx):
        """
        * expand 'k37dcm_prog_slot' program with correct values:
          - slot_idx
          - ?? buffer size ???
          - channel interval (ex: '1001:1018')
          - scancount: number of scans to execute
        * send prog line by line
        """

        log_debug(self, "send_prog_slot(slot_idx=%s)", slot_idx)

        chan_string = self.get_channels_string()
        chan_string = f"{slot_idx}001:{slot_idx}018"

        k37dcm_prog_slot_N = k37dcm_prog_slot.format(
            slot_idx, 2 * 9, chan_string, self.scancount
        )

        for instruction in k37dcm_prog_slot_N.split("\n"):
            if instruction.find("#") == -1:
                log_debug(self, "send_prog_slot: send %s", instruction)
                self.send(instruction)
            else:
                user_print(instruction)
        # user_print ("    --------------------    ")

    def get_channels_string(self):
        """
        Returns the list of channels as a string of chan id separated by ','
        Ex: '4001,4002,4003,4004'
        """
        chan_list_str_comma = ""

        for chan in self.counters:
            if "_ohms" not in chan.name:
                user_print(
                    f"Counter {chan.name}: slot={chan.slot} channel={chan.channel} unit={chan.unit} id={chan.id}"
                )

                chan_list_str_comma += str(chan.id) + ","
        # Removes ending ","...
        chan_list_str = chan_list_str_comma[:-1]

        # print chan_list_str
        return chan_list_str

    def read_channels(self, chan_n):
        """
        """
        self.send(f"bufcnt=dmm.makebuffer({self.chan_count})")
        self.send("bufcnt.clear()")
        self.send("bufcnt.appendmode=1")

        self.wait_end_of_scan()

        read_str = self.read(f"printbuffer({1}, {chan_n}, bufcnt)")
        ret_vals = read_str.split()

        user_print("---------ret_vals-----------")
        user_print(ret_vals)
        user_print("----------------------------")

    def wait_end_of_scan(self):
        t0 = time.time()
        duration = time.time() - t0
        while self.is_scan_running():
            user_print(f"Scan is running...({duration}s)")
            time.sleep(0.5)
            duration = time.time() - t0

        user_print(f"scan duration : {duration}s ")

    def is_scan_running(self):
        if self.get_scan_states()[0] == 2:
            return True
        else:
            return False

    def get_scan_states(self):
        ans = self.read("print(scan.state())")
        log_debug(self, "get scan state: ans=%s", ans)
        # scan.state() returns 4 floats : state, scanCount, stepCount, reading
        # ans looks like : '6.000000e+00\t1.000000e+01\t3.000000e+00\t8.145322e+01'
        # where state can be:
        #  scan.EMPTY or 0
        #  scan.BUILDING or 1
        #  scan.RUNNING or 2
        #  scan.ABORTED or 3
        #  scan.FAILED or 4
        #  scan.FAILED_INIT or 5
        #  scan.SUCCESS or 6
        scan_states = list(map(int, map(float, ans.split("\t"))))
        # user_print "SSS=", scan_states
        return scan_states

    def get_buffer(self):
        buf = self.read(f"printbuffer(1,{self.scancount * self.chan_count},bufM1)")
        return buf

    def read_buffer(self):
        buf = self.get_buffer()
        buf_list = buf.split(", ")
        nb_chan = self.chan_count

        chan_values = dict()
        for ii in range(nb_chan):
            chan_values[ii] = list(map(float, buf_list[ii::nb_chan]))
            if len(chan_values[ii]) == self.scancount:
                user_print(f"ok, {self.scancount} values read.")
            else:
                user_print(
                    f"ERROR: wrong number of values read: {len(chan_values[ii])}"
                )

        return chan_values

    def print_counters(self):
        for chan in self.counters:
            if "_ohms" not in chan.name:
                user_print(
                    f"Counter {chan.name}: slot={chan.slot} channel={chan.channel} unit={chan.unit} id={chan.id}"
                )

    def config_all_slots(self):
        self.config_slot(1)
        self.config_slot(2)
        self.config_slot(3)
        self.config_slot(4)

    def config_slot(self, slot_idx):
        """
        Applies PT100_4W_conf custom configuration to all channels of
        slot number <slot_idx>.
        """
        user_print(f"     ------- CONFIG SLOT {slot_idx} ----------")
        self.send('dmm.func="fourwireohms"')
        self.send("dmm.autorange=dmm.OFF")
        self.send("dmm.aperture=0.02")
        self.send("dmm.linesync=dmm.OFF")
        self.send("dmm.range=100")
        self.send("dmm.nplc=5")
        self.send("dmm.measurecount=1")
        # self.send("dmm.close(\"{}011,{}922\")".format(slot_idx, slot_idx))
        self.send('channel.open("slot{}")'.format(slot_idx))  # open or close ??? :_(
        self.send('channel.setpole("slot{}",4)'.format(slot_idx))
        # ->>> channel.setpole("slot4", 4)

        self.send('dmm.configure.set("PT100_4W_conf")')
        self.send('dmm.setconfig("slot{}", "PT100_4W_conf")'.format(slot_idx))
        # ->>> dmm.setconfig("slot4", "PT100_4W_conf")
        user_print("")


#     def config_all_slots(self):
#         """
#         Applies PT100_4W_conf custom configuration to all channels of
#         all slots.
#         """
#         user_print ("     ------- CONFIG ALL SLOTS ----------")
#         self.send('dmm.func="fourwireohms"')
#         self.send("dmm.autorange=dmm.OFF")
#         self.send("dmm.aperture=0.02")
#         self.send("dmm.linesync=dmm.OFF")
#         self.send("dmm.range=100")
#         self.send("dmm.nplc=5")
#         self.send("dmm.measurecount=1")
#         # self.send("dmm.close(\"{}011,{}922\")".format(slot_idx, slot_idx))
#
#         for i in range(4):
#             self.send('channel.open("slot{}")'.format(i + 1))  # oepn or close ??? :_(
#             self.send('channel.setpole("slot{}",4)'.format(i + 1))
#             # ->>> channel.setpole("slotN", 4)
#
#         self.send('dmm.configure.set("PT100_4W_conf")')
#
#         for i in range(4):
#             self.send('dmm.setconfig("slot{}", "PT100_4W_conf")'.format(i + 1))
#             # ->>> dmm.setconfig("slot4", "PT100_4W_conf")
#         user_print ("")


notes_to_freq4 = {
    "do": 523,
    "re": 587,
    "mi": 659,
    "fa": 698,
    "sol": 783,
    "la": 880,
    "si": 987,
}

notes_to_freq5 = {
    "do": 1046,
    "re": 1174,
    "mi": 1318,
    "fa": 1396,
    "sol": 1567,
    "la": 1760,
    "si": 1975,
}

notes = [
    (0.6, "sol"),
    (0.6, "sol"),
    (0.6, "sol"),
    (0.4, "mi"),
    (0.2, "si"),
    (0.6, "sol"),
    (0.4, "mi"),
    (0.6, "si"),
    (1.2, "sol"),
]
"""
for (nn,tt) in notes:
    k37dcm.comm.write(b"beeper.beep(%g, %d)\n" % (nn, notes_to_freq4[tt]))


"""


"""
AFTER REBOOT / BEFORE CONFIG

SESSION_TEMP [1]: k37dcm.print_slot_config(1)
1: nofunction
2: nofunction
3: nofunction
4: nofunction
5: nofunction
6: nofunction
7: nofunction
8: nofunction
9: nofunction
10: nofunction
11: nofunction
"""

"""
SESSION_TEMP [9]: k37dcm.print_slot_config(1)   # idem 2 3 4
1: PT100_4W_conf
2: PT100_4W_conf
3: PT100_4W_conf
4: PT100_4W_conf
5: PT100_4W_conf
6: PT100_4W_conf
7: PT100_4W_conf
8: PT100_4W_conf
9: PT100_4W_conf
10: PT100_4W_conf
11: PT100_4W_conf
12: PT100_4W_conf
13: PT100_4W_conf
14: PT100_4W_conf
15: PT100_4W_conf
16: PT100_4W_conf
17: PT100_4W_conf
18: PT100_4W_conf
19: PT100_4W_conf
20: PT100_4W_conf
21: nofunction
22: nofunction
"""
