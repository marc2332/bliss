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

"""
ESRF data policy in Bliss
"""

import os
import re
import string
from datetime import datetime
from ..utils import config_utils
from ..io.io_utils import tempdir, tempname


__all__ = ["newexperiment", "newtmpexperiment"]


def filename_templates():
    """
    Templates for HDF5 file names, starting from the dataset
    filename, followed by the master filenames in upper directories.

    :returns list(str):
    """
    return [
        "{sample}_{dataset}.h5",
        os.path.join("..", "{experiment}_{sample}.h5"),
        os.path.join("..", "..", "{experiment}_{beamline}.h5"),
    ]


def subdirectory_template():
    """
    Template for the HDF5 file's subdirectory under `base_path`

    :returns str:
    """
    template = "{experiment}", "{beamline}", "{sample}", "{sample}_{dataset}"
    return os.path.join(*template)


def base_path_template(experiment_type=None, default=None):
    """
    Template for SCAN_SAVING's base_path attribute.

    :param str experiment_type: visitor (official)
                                inhouse (official)
                                tmp (beamline tmp folder)
                                None (local tmp folder)
    :param str default: only used when `experiment_type is None`
    :returns str:
    """
    if experiment_type == "visitor":
        return os.path.join(os.sep, "data", "visitor")
    elif experiment_type == "inhouse":
        subdir = current_month_subdir()
        return os.path.join(os.sep, "data", "{beamline}", "{inhouse_name}", subdir)
    elif experiment_type == "tmp":
        return os.path.join(os.sep, "data", "{beamline}", "tmp")
    else:
        if not default:
            default = tempdir(prefix="bliss")
        return default


def initialize_datapolicy(scan_saving=None):
    """
    Initialize the data policy

    :param bliss.scanning.scan.ScanSaving scan_saving:
    """
    initialize_scan_saving(scan_saving=scan_saving)


def initialize_scan_saving(scan_saving=None):
    """
    Make sure SCAN_SAVING has the data policy template and attributes

    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns bliss.scanning.scan.ScanSaving:
    """
    if scan_saving is None:
        scan_saving = config_utils.current_scan_saving()
    # Add attributes for sub directory template
    defaults = {"beamline": config_utils.beamline()}
    scan_saving.template = subdirectory_template()
    for attr in re.findall(r"\{(.*?)\}", scan_saving.template):
        try:
            getattr(scan_saving, attr)
        except AttributeError:
            scan_saving.add(attr, defaults.get(attr, ""))
    # Add attributes for base directory template
    params = {}
    params["inhouse_name"] = "inhouse"
    for attr, default in params.items():
        try:
            getattr(scan_saving, attr)
        except AttributeError:
            scan_saving.add(attr, default)
    return scan_saving


def current_inhouse_proposal():
    """
    Default proposal name based on beamline and month.
    For example November 2019 at ID21 becomes "id211911".

    :returns str:
    """
    proposal = datetime.now().strftime("{beamline}%y%m")
    proposal = proposal.format(**config_utils.scan_saving_attrs(proposal))
    return proposal


def current_month_subdir():
    """
    Proposals in the inhouse directory are saved per month.
    For example inhouse proposals during November 2019 will be
    saved in inhouse subdirectory "19nov".

    :returns str:
    """
    return datetime.now().strftime("%y%b").lower()


def proposal_root(proposal=None, root=None, managed=True):
    """
    Experiment's base path and proposal

    :param str proposal:
    :param str root:
    :param bool managed: `root` is ignored when `True`
    :returns str, str: base_path, proposal
    """
    scan_saving = initialize_scan_saving()
    if managed:
        root = None
        if proposal:
            proposal = valid_proposal_name(proposal)
            if proposal.startswith("blc") or proposal.startswith("ih"):
                experiment_type = "inhouse"
            else:
                experiment_type = "visitor"
        else:
            proposal = current_inhouse_proposal()
            experiment_type = "inhouse"
    else:
        if proposal:
            proposal = valid_proposal_name(proposal)
        else:
            proposal = tempname(3, chars=string.ascii_lowercase)
            proposal += tempname(3, chars=string.digits)
        if root:
            experiment_type = None
        else:
            experiment_type = "tmp"
    template = base_path_template(experiment_type=experiment_type, default=root)
    base_path = template.format(**config_utils.scan_saving_attrs(template))
    return base_path, proposal


def _newexperiment(proposal=None, root=None, managed=True):
    """
    Set SCAN_SAVING base_path and experiment

    :param str proposal:
    :param str root:
    :param bool managed: `root` is ignored when `True`
    """
    root, proposal = proposal_root(proposal=proposal, root=root, managed=managed)
    scan_saving = initialize_scan_saving()
    scan_saving.base_path = root
    scan_saving.experiment = proposal


def newexperiment(proposal=None):
    """
    Set SCAN_SAVING base_path and experiment

    :param str proposal:
    """
    _newexperiment(proposal=proposal, managed=True)


def newtmpexperiment(proposal=None, root=None):
    """
    Set SCAN_SAVING base_path and experiment

    :param str proposal:
    :param str root:
    """
    _newexperiment(proposal=proposal, root=root, managed=False)


def raise_invalid_characters(pattern, **kwargs):
    """
    :param str pattern: allowed
    :param **kwargs: variables to check
    :raises ValueError:
    """
    mpattern = re.compile(r"^[" + pattern + "]+$")
    for k, v in kwargs.items():
        if not mpattern.match(v):
            raise ValueError(
                "{} {} contains invalid characters (only {} allowed)".format(
                    k, repr(v), repr(pattern)
                )
            )


def raise_invalid_name(pattern, **kwargs):
    """
    :param str pattern: allowed
    :param **kwargs: variables to check
    :raises ValueError:
    """
    mpattern = re.compile(r"^" + pattern + "$")
    for k, v in kwargs.items():
        if not mpattern.match(v):
            raise ValueError(
                "{} {} is invalid (needs to match {})".format(k, repr(v), repr(pattern))
            )


def valid_proposal_name(proposal):
    """
    :param str proposal:
    :returns str: normalized proposal
    """
    raise_invalid_characters(r"0-9a-zA-Z_\s\-", proposal=proposal)
    proposal = proposal.lower()
    proposal = re.sub(r"[^0-9a-z]", "", proposal)
    raise_invalid_name(r"[a-z]+[0-9]+", proposal=proposal)
    return proposal


def valid_beamline_name(beamline):
    """
    :param str beamline:
    :returns str: normalized beamline
    """
    raise_invalid_characters(r"0-9a-zA-Z_\s\-", beamline=beamline)
    beamline = beamline.lower()
    beamline = re.sub(r"[^0-9a-z]", "", beamline)
    raise_invalid_name(r"[a-z]+[0-9]+", beamline=beamline)
    return beamline
