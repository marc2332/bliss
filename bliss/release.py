# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Single source of truth for the version number and the like"""

name = "bliss"
author = "BCU (ESRF)"
author_email = ""
license = "LGPLv3"
copyright = "2016-2018 Beamline Control Unit, ESRF"
description = "BeamLine Instrumentation Support Software"
url = "bliss.gitlab-pages.esrf.fr/bliss"

_version_major = 0
_version_minor = 2
_version_patch = 0
_version_extra = ".dev0"
# _version_extra = ''  # uncomment this for full releases

# Construct full version string from these.
_ver = [_version_major, _version_minor, _version_patch]

version = ".".join(map(str, _ver))
if _version_extra:
    version += _version_extra

# used by the doc
short_version = ".".join(map(str, _ver[:2]))

version_info = _version_major, _version_minor, _version_patch, _version_extra
