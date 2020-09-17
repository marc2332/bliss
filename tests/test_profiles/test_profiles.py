# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from glob import glob
from collections import namedtuple
import numpy
import pytest
from scipy import signal

Dataset = namedtuple("Dataset", ["name", "x", "y", "com", "cen", "fwhm"])


def experimental_data():
    """
    :returns list(Dataset):
    """
    lst = [
        Dataset(
            "calc_gaussian",
            numpy.arange(100),
            signal.gaussian(100, 10),
            pytest.approx(50, abs=1),
            pytest.approx(50, abs=1),
            pytest.approx(23.55, abs=.1),
        )
    ]
    dirname = os.path.dirname(__file__)
    files = glob(os.path.join(dirname, "*.dat"))
    for filename in files:
        com = cen = fwhm = None
        name = os.path.basename(filename)
        data = numpy.loadtxt(filename)
        expected, absdiff = data[0]  # first line of file
        x, y = data[1:].T

        com = cen = pytest.approx(expected, abs=absdiff)
        fwhm = 0

        if name == "cpm18.dat":
            fwhm = pytest.approx(0.0415, abs=0.0001)
        elif name == "cpm18t.dat":
            fwhm = pytest.approx(0.0023, abs=0.0001)
        elif name == "gaussian.dat":
            fwhm = pytest.approx(0.93, abs=0.01)
        elif name == "inverted_gaussian.dat":
            fwhm = pytest.approx(0.93, abs=0.01)
        elif name == "gauss.dat":
            com = None
            fwhm = pytest.approx(2.88, abs=0.01)
        elif name == "permuted_gauss.dat":
            com = None
            fwhm = pytest.approx(2.45, abs=0.01)
        elif name == "off_center_gaussian.dat":
            fwhm = pytest.approx(0.48, abs=0.01)
        elif name == "neg_off_center_gaussian.dat":
            com = None
            fwhm = pytest.approx(0.48, abs=0.01)
        elif name == "triangle.dat":
            fwhm = pytest.approx(1, abs=0.03)
        elif name == "crl.dat":
            fwhm = pytest.approx(0.25, abs=0.01)
        elif name == "stepup.dat":
            com = None
            fwhm = pytest.approx(8.42, abs=0.01)
        elif name == "vibcut.dat":
            com = None
            fwhm = pytest.approx(0.48, abs=0.01)
        elif name == "step_up.dat":
            com = None
            fwhm = 0
        elif name == "step_down.dat":
            com = None
            fwhm = 0
        elif name == "erf_down.dat":
            com = None
            fwhm = pytest.approx(0.54, abs=0.01)
        elif name == "erf_up.dat":
            com = None
            fwhm = pytest.approx(0.54, abs=0.01)
        elif name == "bimodal.dat":
            fwhm = pytest.approx(1.47, abs=0.01)
        elif name == "square.dat":
            fwhm = pytest.approx(0.69, abs=0.01)
        elif name == "sawtooth.dat":
            fwhm = pytest.approx(0.93, abs=0.01)
        elif name == "flat.dat":
            fwhm = 2

        lst.append(Dataset(name, x, y, com, cen, fwhm))
    return lst


def theoretical_profile_parameters():
    """
    :returns list(Dataset):
    """
    return [
        Dataset(
            "gaussian",
            None,
            None,
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.465, abs=.001),
        ),
        Dataset(
            "inverted_gaussian",
            None,
            None,
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.465, abs=.001),
        ),
        Dataset(
            "triangle",
            None,
            None,
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.51, abs=.01),
        ),
        Dataset(
            "flat",
            None,
            None,
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.5, abs=.01),
            pytest.approx(1, abs=.01),
        ),
        Dataset(
            "sawtooth",
            None,
            None,
            pytest.approx(0.5987, abs=.0001),
            pytest.approx(0.6497, abs=.0001),
            pytest.approx(0.47, abs=.01),
        ),
        Dataset(
            "bimodal",
            None,
            None,
            pytest.approx(0.4323, abs=.0001),
            pytest.approx(0.4686, abs=.0001),
            pytest.approx(0.73, abs=.01),
        ),
        Dataset(
            "square",
            None,
            None,
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.5, abs=.01),
            pytest.approx(0.35, abs=.01),
        ),
        Dataset(
            "erf_down",
            None,
            None,
            pytest.approx(0.27, abs=.01),
            pytest.approx(0.52, abs=.01),
            pytest.approx(0.27, abs=.01),
        ),
        Dataset(
            "erf_up",
            None,
            None,
            pytest.approx(0.75, abs=.01),
            pytest.approx(0.52, abs=.01),
            pytest.approx(0.27, abs=.01),
        ),
        Dataset(
            "missing_edge_of_gaussian_right",
            None,
            None,
            pytest.approx(0.875, abs=.01),
            pytest.approx(0.875, abs=.01),
            pytest.approx(0.23, abs=.01),
        ),
        Dataset(
            "missing_edge_of_gaussian_left",
            None,
            None,
            pytest.approx(0.14, abs=.01),
            pytest.approx(0.14, abs=.01),
            pytest.approx(0.23, abs=.01),
        ),
        Dataset(
            "half_gaussian_right",
            None,
            None,
            pytest.approx(0.10, abs=.01),
            pytest.approx(0.06, abs=.01),
            pytest.approx(0.23, abs=.01),
        ),
        Dataset(
            "half_gaussian_left",
            None,
            None,
            pytest.approx(0.91, abs=.01),
            pytest.approx(0.96, abs=.01),
            pytest.approx(0.12, abs=.01),  # underestimation
        ),
    ]
