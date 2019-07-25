# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango attribute as a counter
* counter name can be different than attributre name
* if unit is not specified, unit is taken from tango configuration (if any)
* conversion factor is taken from tango configuration (if any)

TODO :
* alarm ?
* format ?
* writability ?

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



TESTS:
pytest tests/controllers_sw/test_tango_attr_counters.py

Test files:
bliss/tests/controllers_sw/test_tango_attr_counters.py
bliss/tests/test_configuration/tango_attribute_counter.yml

"""

import weakref
from bliss.common.measurement import SamplingCounter
from bliss.common.tango import DeviceProxy
from bliss.common import session
from bliss.common.logtools import *

_CtrGroupReadDict = weakref.WeakValueDictionary()


def get_proxy(tango_uri):
    """Return the Proxy to <tango_uri> Tango device server.
    * Create it if it does not exist.
    * Store existing Proxies in a dict accesible by 'tango_uri' key.
    """

    try:
        return get_proxy.proxies[tango_uri]
    except KeyError:
        # print (f"get_proxy -- create proxy for {tango_uri}")
        pass
    except AttributeError:
        # print (f"get_proxy -- create dict")
        get_proxy.proxies = dict()
        # print (f"get_proxy -- create proxy for {tango_uri}")
    finally:
        get_proxy.proxies[tango_uri] = DeviceProxy(tango_uri)

    return get_proxy.proxies[tango_uri]


def get_attr_config(tango_uri, attr_name):
    """Return configuration of an attribute.
    * Create it if it does not exist.
    * Store config in a dict using 'tango_uri'/'attr_name' as key.
    """

    attr_cfg_key = f"{tango_uri}/{attr_name}"

    try:
        return get_attr_config.config[attr_cfg_key]
    except KeyError:
        pass
    except AttributeError:
        get_attr_config.config = dict()
    finally:
        get_attr_config.config[attr_cfg_key] = get_proxy(
            tango_uri
        ).get_attribute_config(attr_name)

    return get_attr_config.config[attr_cfg_key]


class _CtrGroupRead(object):
    def __init__(self, tango_uri):
        self._tango_uri = tango_uri

        self._counter_names = list()
        self._attributes_config = None
        session.get_current().map.register(self, tag=self.name)

    @property
    def name(self):
        return ",".join(self._counter_names)

    def read_all(self, *counters):
        """Read all attributes at once each time it's requiered.
        """
        # 'cnt.attribute' string is the name of the attribute.
        cnt_list = [cnt.attribute for cnt in counters]

        log_debug(self, f"tango -- {self._tango_uri} -- read_attributes({cnt_list})")
        dev_attrs = get_proxy(self._tango_uri).read_attributes(cnt_list)

        # Check error.
        for attr in dev_attrs:
            error = attr.get_err_stack()
            if error:
                raise PyTango.DevFailed(*error)

        attr_values = [dev_attr.value for dev_attr in dev_attrs]
        log_debug(self, f"tango -- {self._tango_uri} -- values: {attr_values}")
        return attr_values

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

        log_debug(
            self._ctrl, f"             to reflect '{self.attribute}' tango attribute."
        )

        _tango_attr_config = get_attr_config(tango_uri, self.attribute)

        # UNIT
        # Use 'unit' if present in YAML, otherwise, try to read the
        # Tango configured unit.
        yml_unit = config.get("unit")
        tango_unit = _tango_attr_config.unit
        if yml_unit is None:
            if tango_unit != "":
                unit = tango_unit
            else:
                unit = None
        else:
            unit = yml_unit
        log_debug(
            self._ctrl, f"             * unit read from YAML config: '{yml_unit}'"
        )
        log_debug(
            self._ctrl, f"             * unit read from Tango config: '{tango_unit}'"
        )
        log_debug(self._ctrl, f"             * unit used: '{unit}'")

        # DISPLAY_UNIT
        # Use 'display_unit' as conversion factor if present in Tango configuration.
        tango_display_unit = _tango_attr_config.display_unit
        if tango_display_unit != "No display unit":
            self.conversion_factor = float(tango_display_unit)
        else:
            self.conversion_factor = 1

        # INIT
        SamplingCounter.__init__(
            self, name, self._ctrl, unit=unit, conversion_function=self.convert_func
        )

    def convert_func(self, value):
        attr_val = value * self.conversion_factor

        # beurk: workaround to limit the decimals...
        attr_val = int(attr_val * 10000) / 10000

        return attr_val


TangoAttrCounter = tango_attr_as_counter
