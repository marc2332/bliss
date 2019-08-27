# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Access project's data and documentation files.
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# pkg_resources is useful when this package is stored in a zip
# When pkg_resources is not available, the resources dir defaults to the
# directory containing this module.
try:
    import pkg_resources
except ImportError:
    logger.debug("Backtrace", exc_info=True)
    pkg_resources = None


# For packaging purpose, patch this variable to use an alternative directory
# E.g., replace with _RESOURCES_DIR = '/usr/share/pyFAI/data'
_RESOURCES_DIR = None

# For packaging purpose, patch this variable to use an alternative directory
# E.g., replace with _RESOURCES_DIR = '/usr/share/pyFAI/doc'
# Not in use, uncomment when functionnality is needed
# _RESOURCES_DOC_DIR = None

# cx_Freeze frozen support
# See http://cx-freeze.readthedocs.io/en/latest/faq.html#using-data-files
if getattr(sys, "frozen", False):
    # Running in a frozen application:
    # We expect resources to be located either in a pyFAI/resources/ dir
    # relative to the executable or within this package.
    _dir = os.path.join(os.path.dirname(sys.executable), "bliss", "flint", "resources")
    if os.path.isdir(_dir):
        _RESOURCES_DIR = _dir


def resource_filename(resource):
    """Return filename corresponding to resource.
    resource can be the name of either a file or a directory.
    The existence of the resource is not checked.
    :param str resource: Resource path relative to resource directory
                         using '/' path separator.
    :return: Absolute resource path in the file system
    """
    # Not in use, uncomment when functionnality is needed
    # If _RESOURCES_DOC_DIR is set, use it to get resources in doc/ subflodler
    # from an alternative directory.
    # if _RESOURCES_DOC_DIR is not None and (resource is 'doc' or
    #         resource.startswith('doc/')):
    #     # Remove doc folder from resource relative path
    #     return os.path.join(_RESOURCES_DOC_DIR, *resource.split('/')[1:])

    if _RESOURCES_DIR is not None:  # if set, use this directory
        return os.path.join(_RESOURCES_DIR, *resource.split("/"))
    elif pkg_resources is None:  # Fallback if pkg_resources is not available
        return os.path.join(
            os.path.abspath(os.path.dirname(__file__)), *resource.split("/")
        )
    else:  # Preferred way to get resources as it supports zipfile package
        return pkg_resources.resource_filename(__name__, resource)


_already_registered = False


def silx_integration():
    """Register flint resources to the silx resources.

    It make available resources throug silx API, using a prefix."""
    global _already_registered
    if _already_registered:
        return
    import silx.resources

    silx.resources.register_resource_directory("flint", __name__, _RESOURCES_DIR)
    _already_registered = True
