# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2010 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Management of the ICAT dataset in Bliss.

.. autosummary::
    :toctree:

    ingester
"""


class FieldGroup:
    """representation of a techniqe as defined for icat
    fields: all metadata fields requested for this technique
    """

    def __init__(self, name, fields):
        self._name = name
        self._fields = set(fields)

    @property
    def name(self):
        return self._name

    @property
    def fields(self):
        return self._fields

    def __repr__(self):
        return f"<{self._name}:{self._fields}>"
