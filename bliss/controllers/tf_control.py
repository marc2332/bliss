# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import gevent
import gevent.event
import os
import wago_client
import time
import types
import math


class TfWagoMapping:
    def __init__(self, nb_lens, nb_pinhole):
        self.nb_lens = nb_lens
        self.nb_pinhole = nb_pinhole
        self.mapping = []
        self.generate_mapping()

    def __repr__(self):
        return "\n".join(self.mapping)

    def generate_mapping(self):
        STATUS_MODULE = "750-436,%s"
        CONTROL_MODULE = "750-530,%s"
        STATUS = ["status"] * 2
        CONTROL = ["ctrl"]

        """
        There are three types - 0, 1 or 2 pinholes. All the control modules
        and status modules should be consecutive. There are always 2 status
        channels for 1 control channel. The pressure and interlock modules
        are not yet implemented.
        The 750-530 and 750-1515 Digital Output modules are identical.
        The 750-436 and 740-1417 Digital Input modules are identical as well.
        """
        mapping = []
        nb_chan = self.nb_lens + self.nb_pinhole
        ch_ctrl = nb_chan / 8
        ch_stat = (nb_chan * 2) / 8

        if nb_chan > 8:
            ch = nb_chan % 8
            for i in range(ch_ctrl):
                mapping += [CONTROL_MODULE % ",".join(CONTROL * 8)]
            if ch > 0:
                mapping += [CONTROL_MODULE % ",".join(CONTROL * ch + ["_"] * (8 - ch))]
        else:
            mapping += [
                CONTROL_MODULE % ",".join(CONTROL * nb_chan + ["_"] * (8 - nb_chan))
            ]

        ch = nb_chan % 4
        if nb_chan > 4:
            for i in range(ch_stat):
                mapping += [STATUS_MODULE % ",".join(STATUS * 4)]
            if ch > 0:
                mapping += [
                    STATUS_MODULE % ",".join(STATUS * ch + ["_"] * (8 - ch * 2))
                ]
        else:
            if ch > 0:
                mapping += [
                    STATUS_MODULE % ",".join(STATUS * ch + ["_"] * (8 - ch * 2))
                ]
            else:
                mapping += [STATUS_MODULE % ",".join(STATUS * nb_chan)]
        self.mapping = mapping


class TfControl:
    def __init__(self, wago_ip, nb_lens, nb_pinhole, exec_timeout=2):
        self.wago_ip = wago_ip
        self.nb_lens = nb_lens
        if nb_pinhole == 2:
            self.nb_pinhole = 2
            # pinholes are always the first and the last channels
            self.pinhole = [0, (nb_lens + 1)]
        elif nb_pinhole == 1:
            self.nb_pinhole = 1
            # the pinhole is always the first channel
            self.pinhole = 0
        else:
            # set to zero to avoid ambiguous inputs
            self.nb_pinhole = 0

        self.exec_timeout = exec_timeout

    def connect(self):
        self.wago = wago_client.connect(self.wago_ip)
        mapping = TfWagoMapping(self.nb_lens, self.nb_pinhole)
        self.wago.set_mapping(str(mapping), ignore_missing=True)

    def exit(self):
        self.wago.close()

    def pos_read(self):
        stat1 = self.wago.get("status")
        ret = 0
        stat = [num for elem in stat1 for num in elem]
        del stat[(self.nb_lens + self.nb_pinhole) * 2 :]
        for i in range(self.nb_lens + self.nb_pinhole):
            if not stat[2 * i] and stat[2 * i + 1]:
                pos = 0
            elif stat[2 * i] and not stat[2 * i + 1]:
                pos = 1 << i
            else:
                pos = 1 << (i + self.nb_lens + self.nb_pinhole)
            ret += pos
        return ret

    def pos_write(self, value):
        valarr = []
        valarr = [False] * (self.nb_lens + self.nb_pinhole)

        for i in range(self.nb_lens + self.nb_pinhole):
            if value & (1 << i) > 0:
                valarr[i] = True

        valarr.insert(0, "ctrl")
        self.wago.set(valarr)

    def status_read(self):
        stat = []
        mystr = ""
        lbl = ""

        for i in range(self.nb_lens + self.nb_pinhole):
            lbl = "L"
            if self.nb_pinhole > 0:
                if type(self.pinhole) == int:
                    if i == self.pinhole:
                        lbl = "P"
                else:
                    for j in self.pinhole:
                        if i == j:
                            lbl = "P"
            mystr += lbl + str(i + 1) + "  "
        stat.append(mystr)

        value = self.pos_read()
        mystr = ""
        for i in range(self.nb_lens + self.nb_pinhole):
            lbl = "OUT"
            if value & (1 << i) > 0:
                lbl = "IN "
            if value & (1 << i + self.nb_lens + self.nb_pinhole) > 0:
                lbl = "***"
            mystr += lbl + " "
        stat.append(mystr)
        return stat

    def tf_set(self, lenses):
        value = self.pos_read()
        if value >= (1 << (self.nb_lens + self.nb_pinhole)):
            raise RuntimeError("Lenses in unknown position, exiting")
        for i in lenses:
            filt = 1 << i
            if lenses[i] == "in":
                if (value & filt) == 0:
                    value += filt
            else:
                value &= ~filt

        self.pos_write(value)
        check = self.pos_read()
        t0 = time.time()
        while check != value:
            time.sleep(0.5)
            check = self.pos_read()
            if time.time() - t0 > self.exec_timeout:
                raise RuntimeError("Timeout waiting for lenses to be %d" % value)

    def lense_set(self, lense, put_in=True):
        value = self.pos_read()
        if value >= (1 << (self.nb_lens + self.nb_pinhole)):
            raise RuntimeError("Lenses in unknown position, exiting")

        filt = 1 << lense

        if put_in is True:
            if (value & filt) == 0:
                value += filt
        else:
            if (value & filt) != 0:
                value &= ~filt
        self.pos_write(value)

        check = self.pos_read()
        t0 = time.time()
        while check != value:
            time.sleep(0.5)
            check = self.pos_read()
            if time.time() - t0 > self.exec_timeout:
                raise RuntimeError(
                    "Timeout waiting for lense to be %s"
                    % ("in" if put_in is True else "out")
                )

    def tfin(self, lense):
        if self.nb_pinhole == 0:
            if lense >= self.nb_lens:
                raise RuntimeError("Wrong lense number %d" % lense)
            self.lense_set(lense, put_in=True)
        else:
            if lense >= (self.nb_lens + self.nb_pinhole) and lense != 99:
                raise RuntimeError("Wrong lense number %d" % lense)
            if lense == 99:
                # put all the pinhole(s) in, all the lenses out
                value = 0
                if type(self.pinhole) == int:
                    value = 1 << self.pinhole
                else:
                    for i in self.pinhole:
                        value += 1 << i
                self.tfstatus_set(value)
            else:
                if type(self.pinhole) == int:
                    # always put the pinhole together with a lense
                    self.lense_set(self.pinhole, put_in=True)
                    self.lense_set(lense, put_in=True)
                elif type(self.pinhole) == list:
                    lenses = {}
                    value = 0
                    for i in self.pinhole:
                        if i == lense:
                            value = 1 << i
                            self.tfstatus_set(value)
                            return
                        else:
                            for i in self.pinhole:
                                lenses[i] = "out"
                            lenses[lense] = "in"
                    print(lenses)
                    self.tf_set(lenses)

    def tfout(self, lense):
        if lense >= (self.nb_lens + self.nb_pinhole) and lense != 99:
            raise RuntimeError("Wrong lense number %d" % lense)
        if lense == 99:
            if self.nb_pinhole == 0:
                raise RuntimeError("No pinhole configured, command ignored")
            if type(self.pinhole) == int:
                self.lense_set(self.pinhole, put_in=False)
            else:
                for i in self.pinhole:
                    self.lense_set(i, put_in=False)
        self.lense_set(lense, put_in=False)

    def tfsetall(self, flag):
        value = 0
        if flag == True:
            for i in range(self.nb_lens + self.nb_pinhole):
                value += 1 << i
        self.tfstatus_set(value)

    def tfstatus_set(self, value):
        self.pos_write(value)
        t0 = time.time()
        check = self.pos_read()
        while check != value:
            time.sleep(0.5)
            check = self.pos_read()
            if time.time() - t0 > self.exec_timeout:
                raise RuntimeError("Timeout waiting for status to be %d" % value)
