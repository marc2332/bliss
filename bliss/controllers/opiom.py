# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import struct
from warnings import warn

from bliss.comm.util import get_comm, get_comm_type, SERIAL, TCP
from bliss.comm import serial
from bliss.common.greenlet_utils import KillMask, protect_from_kill
from bliss.common.switch import Switch as BaseSwitch
from bliss.config.conductor.client import remote_open

OPIOM_PRG_ROOT = "/users/blissadm/local/isg/opiom"


class Opiom:
    FSIZE = 256

    def __init__(self, name, config_tree):
        self.name = name

        comm_type = None
        try:
            comm_type = get_comm_type(config_tree)
            key = "serial" if comm_type == SERIAL else "tcp"
            config_tree[key]["url"]  # test if url is available
            comm_config = config_tree
        except:
            if "serial" in config_tree:
                comm_type = SERIAL
                comm_config = dict(serial=dict(url=config_tree["serial"]))
                warn(
                    "'serial: <url>' is deprecated. "
                    "Use 'serial: url: <url>' instead",
                    DeprecationWarning,
                )
            elif "socket" in config_tree:
                comm_type = TCP
                comm_config = dict(tcp=dict(url=config_tree["socket"]))
                warn(
                    "'socket: <url>' is deprecated. " "Use 'tcp: url: <url>' instead",
                    DeprecationWarning,
                )
            else:
                raise RuntimeError("opiom: need to specify a communication url")

        if comm_type not in (SERIAL, TCP):
            raise TypeError("opiom: invalid communication type %r" % comm_type)

        self._cnx = get_comm(comm_config, ctype=comm_type, timeout=3)
        self._cnx.flush()
        self.__program = config_tree.get("program", "default")
        self.__base_path = config_tree.get("opiom_prg_root", OPIOM_PRG_ROOT)
        self.__debug = False

        # Sometimes, have to talk twice to the OPIOM in order to get the proper first answer.
        for ii in range(2):
            try:
                msg = self.comm("?VER", timeout=50e-3)
            except serial.SerialTimeout:
                msg = ""

            if msg.startswith("OPIOM"):
                break
        else:
            raise IOError("No opiom connected at %s" % serial)

        self.comm("MODE normal")

    def __info__(self):
        return "opiom: %s" % self._cnx

    @property
    def debug(self):
        return self.__debug

    @debug.setter
    def debug(self, flag):
        self.__debug = bool(flag)

    def __debugMsg(self, wr, msg):
        if self.__debug:
            print("%-5.5s on %s > %s" % (wr, self.name, msg))

    def info(self):
        return self.comm("?INFO")

    def source(self):
        return self.comm("?SRC", timeout=30.)

    def prog(self):
        info = self.info()
        for line in info.split("\n"):
            if line.startswith("PLD prog:"):
                return line.split(":")[1].strip("\n\t ")

    def error(self):
        return self.comm("?ERR")

    def registers(self):
        return {
            "IM": int(self.comm("?IM"), base=16),
            "IMA": int(self.comm("?IMA"), base=16),
        }

    def inputs_stat(self):
        input_front = int(self.comm("?I"), base=16)
        input_back = int(self.comm("?IB"), base=16)

        self._display_bits("I", input_front)
        self._display_bits("IB", input_back)

    def outputs_stat(self):
        output_front = int(self.comm("?O"), base=16)
        output_back = int(self.comm("?OB"), base=16)

        self._display_bits("O", output_front)
        self._display_bits("OB", output_back)

    def raw_write(self, msg):
        self._cnx.write(msg)

    def raw_bin_write(self, binmsg):
        nb_block = len(binmsg) // self.FSIZE
        nb_bytes = len(binmsg) % self.FSIZE
        lrc = (nb_bytes + nb_block + sum([x for x in binmsg])) & 0xff
        rawMsg = struct.pack(
            "BBB%dsBB" % len(binmsg), 0xff, nb_block, nb_bytes, binmsg, lrc, 13
        )
        self._cnx.write(rawMsg)

    def comm_ack(self, msg):
        return self.comm("#" + msg)

    @protect_from_kill
    def comm(self, msg, timeout=None, text=True):
        self._cnx.open()
        with self._cnx._lock:
            self._cnx._write((msg + "\r\n").encode())
            if msg.startswith("?") or msg.startswith("#"):
                msg = self._cnx._readline(timeout=timeout)
                if msg.startswith("$".encode()):
                    msg = self._cnx._readline("$\r\n".encode(), timeout=timeout)
                self.__debugMsg("Read", msg.strip("\n\r".encode()))
                if text:
                    return (msg.strip("\r\n".encode())).decode()
                else:
                    return msg.strip("\r\n".encode())

    def load_program(self, prog_name=None):
        pldid = self.comm("?PLDID")
        if prog_name is None:
            prog_name = self.__program
        if prog_name == "default":
            if pldid == "255":
                # already default
                return
            else:
                print("Uploading default program")
        else:
            try:
                file_pldid, file_project = self._getFilePLDIDandPROJECT(prog_name)
            except ValueError:
                # invalid unpacking
                raise IOError(
                    "opiom %s: cannot find program %s" % (str(self), prog_name)
                )

            s_pldid = str(pldid).encode()
            if file_pldid and file_pldid != s_pldid:
                print("Uploading opiom program, please wait")
                srcsz = int(self.comm("?SRCSZ").split()[0])
                offsets, opmfile = self._getoffset(prog_name)
                if (offsets["src_c"] - offsets["src_cc"]) < srcsz:
                    SRCST = offsets["src_cc"]
                    srcsz = offsets["src_c"] - offsets["src_cc"]
                else:
                    SRCST = offsets["src_c"]
                    srcsz = offsets["jed"] - offsets["src_c"]
                binsz = offsets["size"] - offsets["jed"]

                sendarray = opmfile[SRCST : SRCST + srcsz]
                sendarray += opmfile[offsets["jed"] :]
            else:
                # program already loaded
                self.__debugMsg(
                    "No need to reload opiom program: PLDID did not change", pldid
                )
                return

        if self.comm_ack("MODE program") != "OK":
            raise IOError("Can't program opiom %s" % str(self))

        if prog_name == "default":
            ans = self.comm_ack("PROG DEFAULT")
            sendarray = []
        else:
            ans = self.comm_ack(
                'PROG %d %d %d %d "%s"'
                % (binsz, srcsz, self.FSIZE, int(file_pldid), file_project)
            )
        if ans != "OK":
            self.comm("MODE normal")
            raise IOError("Can't start programming opiom %s" % str(self))

        for frame_n, index in enumerate(range(0, len(sendarray), self.FSIZE)):
            with KillMask():
                cmd = "#*FRM %d\r" % frame_n
                self.raw_write(cmd.encode())
                print("                         ", end="\r")
                print("FRAME {0}".format(frame_n), end="\r")
                self.raw_bin_write(sendarray[index : index + self.FSIZE])
                answer = self._cnx.readline("\r\n".encode())
                if answer[-2:] == b"OK":
                    continue
                raise RuntimeError(
                    "Load program: [%s] returned [%s]" % (cmd.strip(), answer)
                )

        # waiting end programming
        while True:
            stat_num = self.comm("?PSTAT")
            print("                         ", end="\r")
            print("{0}".format(stat_num), end="\r")
            self.__debugMsg("Load", stat_num)
            try:
                stat, percent = stat_num.split()
            except ValueError:
                stat = stat_num
                break
        return stat == "DONE"

    def _display_bits(self, prefix, bits):
        for i in range(1, 9):
            print("%s%d\t" % (prefix, i), end=" ")
        print()
        for i in range(8):
            if (bits >> i) & 0x1:
                print("1\t", end=" ")
            else:
                print("0\t", end=" ")

        print()

    def _getoffset(self, prog_name):
        with remote_open(os.path.join(self.__base_path, prog_name + ".opm")) as f:
            line = f.read(14)
            f.seek(0)
            opmfile = f.read()
            size = f.tell()
        header, src, src_cc, src_c, jed = struct.unpack("<5H", line[3:13])
        return (
            {
                "header": header,
                "src": src,
                "src_cc": src_cc,
                "src_c": src_c,
                "jed": jed,
                "size": size,
            },
            opmfile,
        )

    def _getFilePLDIDandPROJECT(self, prog_name):
        TOKEN = b"#pldid#"
        PROJECT_TOKEN = b"#project#"
        with remote_open(os.path.join(self.__base_path, prog_name + ".opm")) as f:
            begin = -1
            for line in f:
                begin = line.find(TOKEN)
                if begin > -1:
                    break
            if begin > -1:
                subline = line[begin + len(TOKEN) :]
                end = subline.find(TOKEN)
                pldid = subline[:end]

                begin = line.find(PROJECT_TOKEN)
                subline = line[begin + len(PROJECT_TOKEN) :]
                project = subline[: subline.find(PROJECT_TOKEN)]
                return pldid, project


class Switch(BaseSwitch):
    """
    This class wrapped opiom command to emulate a switch
    the configuration may look like this:
    opiom: $opiom_name
    register: IMA
    mask: 0x3
    shift: 1
    states:
       - label: OPEN
         value: 1
       - label: CLOSED
         value: 0
       - label: MUSST
         value: 2
       - label: COUNTER_CARD
         value: 3
    """

    def __init__(self, name, config):
        BaseSwitch.__init__(self, name, config)
        self.__opiom = None
        self.__register = None
        self.__mask = None
        self.__shift = None
        self.__states = dict()

    def _init(self):
        config = self.config
        self.__opiom = config["opiom"]
        self.__register = config["register"]
        self.__mask = config["mask"]
        self.__shift = config["shift"]
        for state in config["states"]:
            label = state["label"]
            value = state["value"]
            self.__states[label] = value

    def _set(self, state):
        value = self.__states.get(state)
        if value is None:
            raise RuntimeError("State %s don't exist" % state)
        mask = self.__mask << self.__shift
        value <<= self.__shift
        cmd = "%s 0x%x 0x%x" % (self.__register, value, mask)
        self.__opiom.comm_ack(cmd)

    def _get(self):
        cmd = "?%s" % self.__register
        value = int(self.__opiom.comm_ack(cmd), base=16)
        value >>= self.__shift
        value &= self.__mask
        for label, state_value in self.__states.items():
            if state_value == value:
                return label
        return "UNKNOWN"

    def _states_list(self):
        return list(self.__states.keys())
