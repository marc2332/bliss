# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import abc
import logging
import numpy
from contextlib import contextmanager
from ..utils.logging_utils import CustomLogger
from ..io import nexus


logger = logging.getLogger(__name__)


class BaseProxy(abc.ABC):
    """
    Wraps HDF5 creation and growth.
    """

    def __init__(self, filename=None, parent=None, filecontext=None, parentlogger=None):
        """
        :param str filename: HDF5 file name
        :param str filecontext: HDF5 open context manager
        :param str parent: path in the HDF5 file
        :param parentlogger:
        """
        if filecontext is None:
            filecontext = self._filecontext
        self.filename = filename
        self.filecontext = filecontext
        self.parent = parent
        if parentlogger is None:
            parentlogger = logger
        self.logger = CustomLogger(parentlogger, self)
        self.npoints = 0
        self.__exists = False

    def __repr__(self):
        if self.name:
            return self.path
        else:
            return os.path.splitext(os.path.basename(self.filename))[0]

    @property
    def path(self):
        if self.name:
            return "/".join([self.parent, self.name])
        else:
            return self.parent

    @property
    def uri(self):
        return self.filename + "::" + self.path

    @abc.abstractproperty
    def name(self):
        pass

    @contextmanager
    def _filecontext(self):
        with nexus.nxRoot(self.filename, mode="a") as nxroot:
            yield nxroot

    def ensure_existance(self):
        with self.filecontext() as nxroot:
            if self.exists:
                return
            self._create(nxroot)

    @abc.abstractmethod
    def _create(self, nxroot):
        pass

    @property
    def exists(self):
        """
        :returns bool:
        """
        if self.__exists:
            return True
        with self.filecontext() as nxroot:
            self.__exists = exists = self.path in nxroot
            return exists

    @contextmanager
    def open(self, ensure_existance=False):
        """
        :param bool ensure_existance:
        :yields h5py.Dataset or None:
        """
        with self.filecontext() as nxroot:
            if ensure_existance:
                self.ensure_existance()
            if self.path in nxroot:
                yield nxroot[self.path]
            else:
                self.logger.warning(repr(self.uri) + " does not exist")
                yield None

    def add(self, newdata):
        """
        Add data

        :param sequence newdata:
        """
        with self.open(ensure_existance=True) as destination:
            try:
                self.npoints += self._insert_data(destination, newdata)
            except TypeError as e:
                self.logger.error(e)
                raise

    @abc.abstractmethod
    def _insert_data(self, destination, newdata):
        """
        Insert new data in dataset

        :param h5py.Dataset or h5py.Group dset:
        :param sequence newdata:
        :returns int: number of added points
        """
        pass

    @property
    def npoints_expected(self):
        return 0

    @property
    def complete(self):
        """
        Variable length scans are marked complete when we have some data
        """
        n, nall = self.npoints, self.npoints_expected
        return n and n >= nall

    @property
    def progress(self):
        if self.npoints_expected:
            return self.npoints / self.npoints_expected
        else:
            if self.npoints:
                return numpy.nan
            else:
                return 0

    @property
    def progress_string(self):
        if self.npoints_expected:
            sortkey = self.npoints / self.npoints_expected
            s = "{:.0f}%".format(sortkey * 100)
        else:
            sortkey = self.npoints
            s = "{:d}pts".format(sortkey)
        return s, sortkey

    @property
    def _progress_log_suffix(self):
        return ""

    def log_progress(self, expect_complete=False):
        """
        :param bool expect_complete: 
        :returns int, bool, str:
        """
        npoints_expected = self.npoints_expected
        npoints_current = self.npoints
        complete = self.complete
        if expect_complete:
            if complete:
                msg = "{}/{} points published{}".format(
                    npoints_current, npoints_expected, self._progress_log_suffix
                )
                self.logger.debug(msg)
            else:
                msg = "only {}/{} points published{}".format(
                    npoints_current, npoints_expected, self._progress_log_suffix
                )
                self.logger.warning(msg)
        else:
            msg = "progress {}/{}{}".format(
                npoints_current, npoints_expected, self._progress_log_suffix
            )
            self.logger.debug(msg)
        return complete
