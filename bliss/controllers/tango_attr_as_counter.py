# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango attribute as a counter

YAML_ configuration example:

.. code-block:: yaml
    - class: tango_attr_as_counter
      uri: orion:10000/fe/id/11
      counters:
        - name: srcur
          attr_name: SR_Current
          unit: mA
        - name: lifetime
          attr_name: SR_Lifetime
"""
import weakref
from bliss.common.measurement import SamplingCounter
from bliss.common.tango import DeviceProxy

_CtrGroupReadDict = weakref.WeakValueDictionary()


class _CtrGroupRead(object):
    def __init__(self, tango_uri):
        self._tango_uri = tango_uri
        self._control = None
        self._counter_names = list()

    @property
    def name(self):
        return ",".join(self._counter_names)

    def read_all(self, *counters):
        if self._control is None:
            self._control = DeviceProxy(self._tango_uri)

        dev_attrs = self._control.read_attributes([cnt.attribute for cnt in counters])
        # Check error
        for attr in dev_attrs:
            error = attr.get_err_stack()
            if error:
                raise PyTango.DevFailed(*error)

        return [dev_attr.value for dev_attr in dev_attrs]

    def add_counter(self, counter_name):
        self._counter_names.append(counter_name)


class tango_attr_as_counter(SamplingCounter):
    def __init__(self, name, config):
        tango_uri = config.get_inherited("uri")
        if tango_uri is None:
            raise KeyError("uri")

        self.attribute = config["attr_name"]
        self._ctrl = _CtrGroupReadDict.setdefault(tango_uri, _CtrGroupRead(tango_uri))
        self._ctrl.add_counter(name)
        SamplingCounter.__init__(self, name, self._ctrl, unit=config.get("unit"))


TangoAttrCounter = tango_attr_as_counter
