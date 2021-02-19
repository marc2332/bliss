# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
ICAT Nexus structure from XML
"""

import os
import re
import numpy
import h5py
import logging
from xml.etree import ElementTree


logger = logging.getLogger(__name__)


nxcharUnicode = h5py.special_dtype(vlen=str)


def singleton(cls):
    instance = cls()
    cls.__new__ = cls.__call__ = lambda cls: instance
    cls.__init__ = lambda self: None
    return instance


@singleton
class IcatToNexus:
    """Convert ICAT metadata fields to a Nexus structure
    """

    _NON_HDF5_ATTRIBUTES = ["groupName", "NAPItype", "record", "ref"]
    _ICAT_FIELD_REGEX = re.compile(r"\A\${(.*)}\Z")

    def __init__(self):
        self.fieldmap = dict()
        xmlroot = ElementTree.parse(
            os.path.join(os.path.dirname(__file__), "hdf5_cfg.xml")
        ).getroot()
        self._parse_xml_node(xmlroot, [])

    def _parse_xml_node(self, xmlnode, parents):
        """Add xmlnode to the ICAT field map recursively
        """
        if xmlnode.tag == "group":
            # HDF5 group
            if parents:
                parents[-1]["name"] = xmlnode.get("groupName")
                parents[-1]["nxdict"].update(self._iter_hdf5_attributes(xmlnode))
        elif xmlnode.tag == "link":
            # HDF5 link:
            if parents:
                linkname = xmlnode.get("groupName")
                linkdest = xmlnode.get("ref")
                parents[-1]["nxdict"][">" + linkname] = linkdest
        else:
            # HDF5 dataset
            m = self._ICAT_FIELD_REGEX.match(xmlnode.text)
            if m:
                dset_name = xmlnode.tag
                field_name = m.group(1)
                napitype = xmlnode.get("NAPItype")
                attrs = {
                    dset_name + k: v for k, v in self._iter_hdf5_attributes(xmlnode)
                }
                self.fieldmap[field_name] = {
                    "name": dset_name,
                    "nxdict": attrs,
                    "napitype": napitype,
                    "parents": parents,
                }

        # Recurse
        for xmlchildnode in xmlnode:
            if xmlchildnode.tag == "group":
                rparents = parents + [{"nxdict": {}}]
            else:
                rparents = parents
            self._parse_xml_node(xmlchildnode, rparents)

    @classmethod
    def _iter_hdf5_attributes(cls, xmlnode):
        """Get HDF5 attributes from an XML node
        """
        for aname, avalue in xmlnode.items():
            if aname in cls._NON_HDF5_ATTRIBUTES or aname.startswith("ESRF_"):
                continue
            yield "@" + aname, avalue

    @classmethod
    def _convert_nx_type(cls, value, napitype):
        """Nexus convert to the Nexus type as defined in the XML file
        """
        if napitype == "NX_CHAR" or napitype is None:
            return numpy.array(value, nxcharUnicode)
        elif napitype == "NX_DATE_TIME":
            if not isinstance(value, str):
                value = value.isoformat(value)
            return cls._convert_nx_type(value, "NX_CHAR")
        elif napitype == "NX_INT":
            return int(value)
        else:
            return float(value)

    def create_nxtreedict(self, metadict):
        """Convert ICAT metadata fields to a `dict` for `dicttonx`
        """
        nxtreedict = {}
        for fieldname, fieldvalue in metadict.items():
            # Get the Nexus info
            dsetinfo = self.fieldmap.get(fieldname)
            if dsetinfo is None:
                logger.warning(f"{fieldname} not a valid ICAT field")
                continue
            # Get direct parent
            parent = nxtreedict
            for p in dsetinfo["parents"]:
                if p["name"] not in parent:
                    parent[p["name"]] = dict(p["nxdict"])
                parent = parent[p["name"]]
            # Add dataset to parent
            parent.update(dsetinfo["nxdict"])
            parent[dsetinfo["name"]] = self._convert_nx_type(
                fieldvalue, dsetinfo["napitype"]
            )
        return nxtreedict
