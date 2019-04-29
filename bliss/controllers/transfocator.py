# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
ESRF Transfocator

Example YAML_ configuration:

.. code-block:: yaml

    plugin: bliss
    class: Transfocator
    name: t1
    lenses: 8                    # (1)
    pinhole: 1                   # (2)
    safety: True                 # (3)
    controller_ip: 192.168.1.1   # (4)

1. number of lenses (mandatory)
2. number of pinholes [0..2]. If 1, assumes pinhole is at beginning.
   If 2, assumes pinholes are at beginning and end (mandatory)
3. If safety is active forces a pinhole in if any lens is in
   (optional, default: False)
4. wago adress (mandatory)

Usage::

    >>> from bliss.config.static import get_config
    >>> config = get_config()
    >>> t1 = config.get('t1')

    >>> # repr gives view of transfocator
    >>> t1
    P0  L1  L2   L3  L4  L5   L6  L7   L8
    IN  IN  OUT  IN  IN  OUT  IN  OUT  OUT

    >>> # acess items as list
    >>> t1[1]
    'IN'

    # multiple values work as well
    >>> t1[3, 5]
    ['IN', 'OUT']

    # so do slices
    >>> t1[:]
    ['IN', 'IN', 'OUT', 'IN', 'IN', 'OUT', 'IN', 'OUT', 'OUT']

    # take individual lens out (may use 0, False, 'out' or 'OUT')
    >>> t1[1] = 0

    >>> # multiple lenses at same time
    >>> t1[2, 5] = 'out', 'in'

    >>> # shortcut to put multiple at same place
    >>> t1[1:6] = 1       # put everything IN
"""

import sys
import gevent
import os
import time
import types
import math
import tabulate
from bliss.common.utils import grouped
from bliss.controllers.wago import WagoController
from bliss.config import channels
from bliss.common.event import dispatcher


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
        ch_ctrl = nb_chan // 8
        ch_stat = (nb_chan * 2) // 8

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


def _display(status):
    return "---" if status is None else ("IN" if status else "OUT")


def _encode(status):
    if status in (1, "in", "IN", True):
        return True
    elif status in (0, "out", "OUT", False):
        return False
    raise ValueError("Invalid position {!r}".format(status))


class Transfocator:
    def __init__(self, name, config):
        self.exec_timeout = int(config.get("timeout", 3))
        # read_mode 0 means:
        # 'first transfocator in beam status is wired first in Wago',
        # read_mode >0 means:
        # 'first transfocator in beam status is wired last in Wago'
        # the same goes for cmd_mode
        self.name = name
        self.read_mode = int(config.get("read_mode", 0))
        self.cmd_mode = int(config.get("cmd_mode", 0))
        self.safety = bool(config.get("safety", False))
        self.wago_ip = config["controller_ip"]
        self.wago = None
        self.empty_jacks = []
        self.pinhole = []
        self._state_chan = channels.Channel(
            "transfocator:%s" % name, callback=self.__state_changed
        )

        if "lenses" in config:
            self.nb_lens = int(config["lenses"])
            nb_pinhole = int(config["pinhole"])

            if nb_pinhole == 2:
                self.nb_pinhole = 2
                # pinholes are always the first and the last channels
                self.pinhole = [0, self.nb_lens - 1]
            elif nb_pinhole == 1:
                self.nb_pinhole = 1
                # the pinhole is always the first channel
                self.pinhole = [0]
            else:
                # set to zero to avoid ambiguous inputs
                self.nb_pinhole = 0
        else:
            layout = config["layout"].strip()
            lenses = []
            for i, c in enumerate(layout.split()):
                if c == "X":
                    self.empty_jacks.append(i)
                elif c == "P":
                    self.pinhole.append(i)
                elif c == "L":
                    lenses.append(i)
                else:
                    raise ValueError("%s: layout: unknown element `%s'" % (name, c))

            if len(self.pinhole) > 2:
                raise ValueError("%s: layout can only have 2 pinholes maximum" % name)

            self.nb_lens = len(lenses) + len(self.empty_jacks)
            self.nb_pinhole = len(self.pinhole)

    def connect(self):
        if self.wago is None:
            self.wago = WagoController(self.wago_ip)
            mapping = TfWagoMapping(self.nb_lens, self.nb_pinhole)
            self.wago.set_mapping(str(mapping), ignore_missing=True)

    def pos_read(self):
        self.connect()

        state = list(grouped(self.wago.get("status"), 2))
        if self.read_mode != 0:
            state.reverse()

        bits = 0
        for i, (s, t) in enumerate(state):
            if i in self.empty_jacks:
                continue
            if s and not t:
                bits += 1 << i  # (1 << n-i)

        return bits

    def pos_write(self, value):
        self.connect()

        valarr = [False] * (self.nb_lens + self.nb_pinhole)

        for i in range(self.nb_lens + self.nb_pinhole):
            if value & (1 << i) > 0:
                valarr[i] = True

        if self.cmd_mode != 0:
            valarr.reverse()

        valarr.insert(0, "ctrl")
        self.wago.set(valarr)

    def tfstatus_set(self, value):
        self.pos_write(value)
        try:
            check = self.pos_read()
            with gevent.Timeout(
                self.exec_timeout,
                RuntimeError("Timeout waiting for status to be %d" % value),
            ):
                while check != value:
                    time.sleep(0.2)
                    check = self.pos_read()
        finally:
            self._state_chan.value = self.status_read()

    def status_dict(self):
        positions = {}
        value = self.pos_read()
        for i in range(self.nb_lens + self.nb_pinhole):
            if i in self.empty_jacks:
                lbl, position = "X{}", None
            else:
                lbl = "P{}" if i in self.pinhole else "L{}"
                position = value & (1 << i) > 0
            positions[lbl.format(i)] = position
        return positions

    def status_read(self):
        header, positions = zip(*self.status_dict().items())
        header = "".join(("{:<4}".format(col) for col in header))
        positions = (_display(col) for col in positions)
        positions = "".join(("{:<4}".format(col) for col in positions))
        return header, positions

    def set(self, *lenses):
        status = len(self) * [False]
        for i, lense in enumerate(lenses):
            status[i] = lense
        self[:] = status

    def set_in(self, lense_index):
        self[lense_index] = True

    def set_out(self, lense_index):
        self[lense_index] = False

    def toggle(self, lense_index):
        current_bits = self.pos_read()
        self[lense_index] = current_bits & (1 << lense_index) == 0

    def set_n(self, *idx_values):
        bits = self.pos_read()
        for idx, value in zip(idx_values[::2], idx_values[1::2]):
            if value is None or idx in self.empty_jacks:
                continue
            else:
                if _encode(value):
                    bits |= 1 << idx
                else:
                    bits &= 0xFFFFFFFF ^ (1 << idx)
        if self.safety and bits and self.pinhole:
            for pinhole in self.pinhole:
                bits |= 1 << pinhole
        if self.pos_read() == bits:
            # nothing to do
            return
        self.tfstatus_set(bits)

    def set_all(self, set_in=True):
        self[:] = set_in

    def set_pin(self, set_in=True):
        self[self.pinhole] = set_in

    def __state_changed(self, st):
        dispatcher.send("state", self, st)

    def __len__(self):
        return self.nb_lens + self.nb_pinhole

    def __getitem__(self, idx):
        pos = list(self.status_dict().values())
        if isinstance(idx, int):
            return _display(pos[idx])
        elif isinstance(idx, slice):
            idx = list(range(*idx.indices(self.nb_lens + self.nb_pinhole)))
        return [_display(pos[i]) for i in idx]

    def __setitem__(self, idx, value):
        if isinstance(idx, int):
            args = idx, value
        else:
            if isinstance(idx, slice):
                idx = list(range(*idx.indices(self.nb_lens + self.nb_pinhole)))
            nb_idx = len(idx)
            if not isinstance(value, (tuple, list)):
                value = nb_idx * [value]
            nb_value = len(value)
            if nb_idx != nb_value:
                raise ValueError(
                    "Mismatch between number of lenses ({}) "
                    "and number of values ({})".format(nb_idx, nb_value)
                )
            args = [val for pair in zip(idx, value) for val in pair]
        self.set_n(*args)

    def __repr__(self):
        prefix = "Transfocator " + self.name
        try:
            header, positions = list(zip(*list(self.status_dict().items())))
            positions = [_display(col) for col in positions]
            table = tabulate.tabulate((header, positions), tablefmt="plain")
            return "{}:\n{}".format(prefix, table)
        except Exception as err:
            return "{}: Error: {}".format(prefix, err)

    def __str__(self):
        # Channel uses louie behind which calls this object str.
        # str is overloaded to avoid calling repr which triggers a connection.
        # We want to avoid creating a connection just because of a louie signal
        return (
            "<bliss.controllers.transfocator.Transfocator "
            "instance at {:x}>".format(id(self))
        )
