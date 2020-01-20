# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging
from .base_proxy import BaseProxy
from ..io import nexus


logger = logging.getLogger(__name__)


class ReferenceProxy(BaseProxy):
    """
    Wraps HDF5 link creating and growth.
    """

    def __init__(
        self,
        filename=None,
        parent=None,
        filecontext=None,
        nreferences=0,
        parentlogger=None,
    ):
        """
        :param str filename: HDF5 file name
        :param str filecontext: HDF5 open context manager
        :param str parent: path in the HDF5 file
        :param int nreferences: variable length by default
        :param parentlogger:
        """
        if parentlogger is None:
            parentlogger = logger
        super().__init__(
            filename=filename,
            parent=parent,
            filecontext=filecontext,
            parentlogger=parentlogger,
        )
        self.nreferences = nreferences

    @property
    def name(self):
        return ""

    @property
    def npoints_expected(self):
        return self.nreferences

    def add_references(self, newuris):
        """
        Add uri links

        :param list(str) newuris:
        """
        self.add(newuris)

    def _insert_data(self, group, newuris):
        """
        Add uri links

        :param list(str) newuris:
        :returns int: added links
        """
        for uri in newuris:
            linkname = nexus.splitUri(uri)[1].split("/")[-1]
            nexus.createLink(group, linkname, uri)
        return len(newuris)

    def _create(self, nxroot):
        """
        Create the group which will contain the links
        """
        nxroot.create_group(self.path)
