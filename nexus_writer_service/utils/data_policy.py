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


__all__ = [
    "newvisitor",
    "newinhouse",
    "newtmpexperiment",
    "newdefaultexperiment",
    "newlocalexperiment",
]


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
                                default (unofficial inhouse)
                                tmp (beamline temp folder)
                                None (local temp folder)
    :param str default: used when `experiment_type is None`
    :returns str:
    """
    if experiment_type == "visitor":
        return os.path.join(os.sep, "data", "visitor")
    elif experiment_type == "inhouse":
        subdir = current_inhouse_subdir()
        return os.path.join(os.sep, "data", "{beamline}", "{inhouse_name}", subdir)
    elif experiment_type == "default":
        subdir = "default"
        return os.path.join(os.sep, "data", "{beamline}", "{inhouse_name}", subdir)
    elif experiment_type == "tmp":
        root = os.path.join(os.sep, "data", "{beamline}", "tmp")
        return tempdir(root=root, prefix="bliss")
    else:
        if not default:
            default = tempdir(prefix="bliss")
        return default


def initialize_datapolicy():
    """
    Initialize the data policy
    """
    initialize_scan_saving()


def initialize_scan_saving():
    """
    Make sure SCAN_SAVING has the data policy template and attributes

    :returns SCAN_SAVING:
    """
    scan_saving = config_utils.scan_saving()
    # Attributes for sub directory template
    defaults = {"beamline": config_utils.beamline()}
    scan_saving.template = subdirectory_template()
    for attr in re.findall(r"\{(.*?)\}", scan_saving.template):
        try:
            getattr(scan_saving, attr)
        except AttributeError:
            scan_saving.add(attr, defaults.get(attr, ""))
    # Attributes for base directory template
    params = {}
    params["inhouse_name"] = "inhouse"
    for attr, default in params.items():
        try:
            getattr(scan_saving, attr)
        except AttributeError:
            scan_saving.add(attr, default)
    return scan_saving


def current_default_proposal():
    """
    Default proposal name based on beamline and month.
    For example November 2019 and ID21 becomes "id211911".

    :returns str:
    """
    proposal = datetime.now().strftime("{beamline}%y%m")
    proposal = proposal.format(**config_utils.scan_saving_attrs(proposal))
    return proposal


def current_inhouse_subdir():
    """
    Proposals in the inhouse directory are saved per month.
    For example inhouse proposals during November 2019 will be saved in inhouse subdirectory "19nov".

    :returns str:
    """
    return datetime.now().strftime("%y%b").lower()


def base_path(proposal=None, experiment_type=None, root=None):
    """
    Experiment's base path and proposal

    :param str proposal:
    :param str experiment_type: see `base_path_template`
    :param str root: see `base_path_template`
    :returns str, str: base_path, proposal
    """
    scan_saving = initialize_scan_saving()
    if not proposal:
        if experiment_type == "inhouse":
            experiment_type = "default"
        if experiment_type == "default":
            proposal = current_default_proposal()
        elif experiment_type not in ["visitor", "inhouse"]:
            proposal = tempname(3, chars=string.ascii_lowercase)
            proposal += tempname(3, chars=string.digits)
        if not proposal:
            raise ValueError(
                "Experiment type {} needs a proposal name".format(repr(experiment_type))
            )
    template = base_path_template(experiment_type=experiment_type, default=root)
    base_path = template.format(**config_utils.scan_saving_attrs(template))
    proposal = valid_proposal_name(proposal)
    return base_path, proposal


def newexperiment(**kwargs):
    """
    Set SCAN_SAVING base_path and experiment

    :param **kwargs: see `base_path`
    """
    root, proposal = base_path(**kwargs)
    scan_saving = initialize_scan_saving()
    scan_saving.base_path = root
    scan_saving.experiment = proposal


def newvisitor(proposal):
    """
    Set experiment root in SCAN_SAVING base_path
    to "/data/visitor"

    :param str proposal:
    """
    newexperiment(proposal=proposal, experiment_type="visitor")


def newinhouse(proposal):
    """
    Set experiment root in SCAN_SAVING base_path
    to "/data/{beamline}/{inhouse_name}/%y%b".

    :param str proposal: same as `newdefaultexperiment` when not specified
    """
    newexperiment(proposal=proposal, experiment_type="inhouse")


def newdefaultexperiment():
    """
    Set experiment root in SCAN_SAVING base_path
    to "/data/{beamline}/{inhouse_name}/default"
    and experiment to "{beamline}%y%m"
    """
    newexperiment(experiment_type="default")


def newtmpexperiment(proposal=None):
    """
    Set experiment root in SCAN_SAVING base_path
    to "/data/{beamline}/tmp"

    :param str proposal: random name when not specified
    """
    newexperiment(proposal=proposal, experiment_type="tmp")


def newlocalexperiment(proposal=None, root=None):
    """
    Set experiment root in SCAN_SAVING base_path
    to root

    :param str proposal: random name when not specified
    :param str root: system tmp directory when not specified
    """
    newexperiment(proposal=proposal, root=root)


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
