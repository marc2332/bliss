# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from bliss.icat import FieldGroup
from xml.etree import ElementTree
from collections import namedtuple
from bliss.common.utils import autocomplete_property


def process_node(n, fields):
    """adds recursively all children to fields (a list that has to be provieded)"""
    text = n.text.strip("${}\n ")
    if text != "":
        fields.append(text)
    for child in n:
        process_node(child, fields)


def singleton(cls):
    instance = cls()
    cls.__new__ = cls.__call__ = lambda cls: instance
    cls.__init__ = lambda self: None
    return instance


@singleton
class Definitions:
    def __init__(self):
        self._populate()

    def _populate(self):
        """ used on modul import to initialize globals of this module
        """
        # open config xml
        xml = ElementTree.parse(os.path.join(os.path.dirname(__file__), "hdf5_cfg.xml"))

        # populate TECHNIQUES
        TECHNIQUES = dict()
        for techniques in xml.iterfind('.//group[@NX_class="NXsubentry"]'):
            fields = list()
            tech_name = techniques.get("groupName")
            for y in techniques:
                if y.tag != "link":
                    process_node(y, fields)

            TECHNIQUES[tech_name] = FieldGroup(tech_name, fields)
            self._techniques = self._make_named_tuple("techniques", TECHNIQUES)

        # populate INSTRUMENTATION
        # dict that contains all known instumentation groups
        INSTRUMENTATION = dict()
        inst_entry = xml.find('.//group[@NX_class="NXinstrument"]')
        glob_inst_fields = list()
        for y in inst_entry:
            if len(y) == 0:
                text = y.text.strip("${}\n ")
                glob_inst_fields.append(text)
                continue

            fields = list()
            inst_group_name = y.get("groupName")

            for inst_field in y:
                process_node(y, fields)

            INSTRUMENTATION[inst_group_name] = FieldGroup(inst_group_name, fields)

        INSTRUMENTATION["instrument"] = FieldGroup("instrument", glob_inst_fields)
        self._instrumentation = self._make_named_tuple(
            "instrumentation", INSTRUMENTATION
        )

        # populate POSITIONERS
        # dict that contains all known positiner groups
        POSITIONERS = dict()
        for pos_parent in xml.iterfind('.//group[@NX_class="NXpositioner"]/..'):
            fields = list()
            pos_group_name = pos_parent.get("groupName")

            if pos_group_name == "instrument":
                process_node(
                    pos_parent.find('.//group[@NX_class="NXpositioner"]'), fields
                )
            else:
                for pos in pos_parent.iterfind('.//group[@NX_class="NXpositioner"]'):
                    if pos.get("groupName") != "positioners":
                        # deal with insertion device / nested positioners declaration
                        fields2 = list()
                        pos_group_name2 = pos_group_name + "_" + pos.get("groupName")
                        process_node(pos, fields2)
                        POSITIONERS[pos_group_name2] = FieldGroup(
                            pos_group_name2, sorted(fields2)
                        )

                    else:
                        process_node(pos, fields)

            if fields:
                POSITIONERS[pos_group_name] = FieldGroup(pos_group_name, sorted(fields))
        self._positioners = self._make_named_tuple("positioners", POSITIONERS)

        # populate SAMPLE
        sample_entry = xml.find('.//group[@NX_class="NXsample"]')
        fields = list()

        for y in sample_entry:
            process_node(y, fields)

        self._sample = FieldGroup("Sample", sorted(fields))

        # populate NOTES
        fields = list()
        for notes_entry in xml.iterfind('.//group[@NX_class="NXnote"]'):
            for y in notes_entry:
                process_node(y, fields)

        self._notes = FieldGroup("Notes", sorted(fields))

        # populate ALL
        # set that contains all fields defined in icat
        ALL = set()
        for entry in xml.iter():
            if not entry.text:
                continue

            text = entry.text.strip("${}\n ")
            if text != "":
                ALL.add(text)
        self._all = tuple(ALL)

    def _make_named_tuple(self, name, dct):
        tup_class = namedtuple(name, dct)
        return tup_class(**dct)

    @autocomplete_property
    def positioners(self):
        return self._positioners

    @autocomplete_property
    def instrumentation(self):
        return self._instrumentation

    @autocomplete_property
    def techniques(self):
        return self._techniques

    @autocomplete_property
    def all(self):
        return self._all

    @autocomplete_property
    def notes(self):
        return self._notes

    @autocomplete_property
    def sample(self):
        return self._sample
