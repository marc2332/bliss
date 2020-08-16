# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango number attribute as a counter:
* counter name can be different than attributre name
* if unit is not specified, unit is taken from tango configuration (if any)
* conversion factor is taken from tango configuration (if any)

TODO :
* alarm ?
* writability ?
* string attribute
* spectrum attribute (tango_attr_as_spectrum ?)
* image attribute (tango_attr_as_image ?)

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
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.common import tango
from bliss import global_map
from bliss.common.logtools import log_debug, log_warning

from bliss.controllers.counter import SamplingCounterController

_TangoCounterControllerDict = weakref.WeakValueDictionary()


def get_attr_config(tango_dev, attr_name):
    """Return configuration of an attribute.
    * Create it if it does not exist.
    * Store config in a dict using 'tango_uri'/'attr_name' as key.
    """
    return tango_dev.get_attribute_config(attr_name)


"""
Example of get_attr_config(self.tango_uri, self.attribute)

AttributeInfoEx[
            alarms = AttributeAlarmInfo(delta_t = 'Not specified', delta_val = 'Not specified',
                                        extensions = [], max_alarm = 'Not specified',
                                        max_warning = 'Not specified', min_alarm = 'Not specified',
                                        min_warning = 'Not specified')
       data_format = tango._tango.AttrDataFormat.SCALAR
         data_type = tango._tango.CmdArgType.DevFloat
       description = 'No description'
        disp_level = tango._tango.DispLevel.OPERATOR
      display_unit = 'No display unit'
       enum_labels = []
            events = AttributeEventInfo(arch_event = ArchiveEventInfo(archive_abs_change = 'Not specified', 
                                                                      archive_period = 'Not specified', 
                                                                      archive_rel_change = 'Not specified', 
                                                                      extensions = []), 
                                        ch_event = ChangeEventInfo(abs_change = 'Not specified', 
                                                                   extensions = [], 
                                                                   rel_change = 'Not specified'), 
                                        per_event = PeriodicEventInfo(extensions = [], period = '1000'))
        extensions = []
            format = '%6.2f'
             label = 'hppstc1'
         max_alarm = 'Not specified'
         max_dim_x = 1
         max_dim_y = 0
         max_value = 'Not specified'
         memorized = tango._tango.AttrMemorizedType.NOT_KNOWN
         min_alarm = 'Not specified'
         min_value = 'Not specified'
              name = 'hppstc1'
    root_attr_name = ''
     standard_unit = 'No standard unit'
    sys_extensions = []
              unit = ''
          writable = tango._tango.AttrWriteType.READ
writable_attr_name = 'None']
"""


class TangoCounterController(SamplingCounterController):
    def __init__(self, name, tango_uri, global_map_register=True):
        super().__init__(name=name)

        self._tango_uri = tango_uri
        self._proxy = tango.DeviceProxy(tango_uri)
        self._attributes_config = None
        if global_map_register:
            global_map.register(self, tag=self.name, children_list=[self._proxy])

    def read_all(self, *counters):
        """
        Read all attributes at once each time it's required.
        """

        # Build list of attribute names (str) to read (attributes must be unique).
        attributes_to_read = list()
        for cnt in counters:
            if cnt.attribute not in attributes_to_read:
                attributes_to_read.append(cnt.attribute)

        log_debug(
            self, "TAAC--%s--attributes_to_read=%s", self._tango_uri, attributes_to_read
        )

        dev_attrs = self._proxy.read_attributes(attributes_to_read)

        # Check error.
        for attr in dev_attrs:
            error = attr.get_err_stack()
            if error:
                raise tango.DevFailed(*error)

        attr_values = [dev_attr.value for dev_attr in dev_attrs]

        # Make a dict to ease counters affectation:
        #   keys->attributes, items->values
        attributes_values = dict(zip(attributes_to_read, attr_values))

        counters_values = list()
        for cnt in counters:
            if cnt.index is None:
                counters_values.append(attributes_values[cnt.attribute])
            else:
                counters_values.append(attributes_values[cnt.attribute][cnt.index])

        log_debug(self, "TAAC--%s--values: %s", self._tango_uri, counters_values)
        return counters_values


class tango_attr_as_counter(SamplingCounter):
    def __init__(self, name, config, controller=None):
        self.index = None

        self.tango_uri = config.get_inherited("uri")
        if self.tango_uri is None:
            raise KeyError("uri")

        self.attribute = config["attr_name"]

        try:
            self.index = config["index"]
        except Exception:
            # no index present -> scalar
            pass

        if controller is None:
            # a controller is not provided => it is a stand-alone counter from config,
            # use a generic controller, readings will be grouped by Tango device
            # to optimise as much as possible
            # the controller name is
            controller = _TangoCounterControllerDict.setdefault(
                self.tango_uri,
                TangoCounterController("generic_tg_controller", self.tango_uri),
            )

        log_debug(
            controller, "             to read '%s' tango attribute.", self.attribute
        )

        _tango_attr_config = get_attr_config(controller._proxy, self.attribute)

        # UNIT
        # Use 'unit' if present in YAML, otherwise, try to use the
        # Tango configured 'unit'.
        self.yml_unit = config.get("unit")
        self.tango_unit = _tango_attr_config.unit
        if self.yml_unit is None:
            if self.tango_unit != "":
                unit = self.tango_unit
            else:
                unit = None
        else:
            unit = self.yml_unit
        log_debug(
            controller, "             * unit read from YAML config: '%s'", self.yml_unit
        )
        log_debug(
            controller,
            "             * unit read from Tango config: '%s'",
            self.tango_unit,
        )
        log_debug(controller, "             * unit used: '%s'", unit)

        # DISPLAY_UNIT
        # Use 'display_unit' as conversion factor if present in Tango configuration.
        tango_display_unit = _tango_attr_config.display_unit

        try:
            if tango_display_unit != "None" and tango_display_unit != "No display unit":
                self.conversion_factor = float(tango_display_unit)
            else:
                self.conversion_factor = 1
        except (ValueError, TypeError):
            log_warning(
                controller,
                "display_unit '%s' cannot be converted to a float. Using 1 as Conversion factor for counter.",
                name,
            )
            self.conversion_factor = 1

        # Sampling MODE.
        # MEAN is the default, like all sampling counters
        sampling_mode = config.get("mode", SamplingMode.MEAN)

        # FORMAT
        # Use 'format' if present in YAML, otherwise, try to use the
        # Tango configured 'format'.
        # default: %6.2f
        self.yml_format = config.get("format")
        self.tango_format = _tango_attr_config.format
        if self.yml_format:
            self.format_string = self.yml_format
        else:
            self.format_string = self.tango_format

        # INIT
        SamplingCounter.__init__(
            self,
            name,
            controller,
            conversion_function=self.convert_func,
            mode=sampling_mode,
            unit=unit,
        )

    def __info__(self):
        info_string = f"'{self.name}` Tango attribute counter info:\n"
        info_string += f"  device server = {self.tango_uri}\n"
        info_string += f"  Tango attribute = {self.attribute}\n"

        # FORMAT
        if self.yml_format is not None:
            info_string += f'  Beacon format = "{self.yml_format}"\n'
        else:
            if self.tango_format != "":
                info_string += f'  Tango format = "{self.tango_format}"\n'
            else:
                info_string += f"  no format\n"

        # UNIT
        if self.yml_unit is not None:
            info_string += f'  Beacon unit = "{self.yml_unit}"\n'
        else:
            if self.tango_unit != "":
                info_string += f'  Tango unit = "{self.tango_unit}"\n'
            else:
                info_string += f"  no unit\n"

        # INDEX if any
        if self.index is not None:
            info_string += f"  index: {self.index}\n"
        else:
            info_string += f"  scalar\n"

        # VALUE
        info_string += f"  value: {self.value}\n"

        return info_string

    def convert_func(self, raw_value):
        """
        Apply to the <raw_value>:
        * conversion_factor
        * formatting
        """
        log_debug(self, "raw_value=%s", raw_value)
        attr_val = raw_value * self.conversion_factor
        formated_value = float(
            self.format_string % attr_val if self.format_string else attr_val
        )
        return formated_value

    @property
    def value(self):
        """
        Return value of the attribute WITH conversion.
        """
        value = self.convert_func(self.raw_value)
        return value

    @property
    def raw_value(self):
        attr_value = self.raw_read
        if self.index is not None:
            value = attr_value[self.index]
        else:
            value = attr_value

        return value


TangoAttrCounter = tango_attr_as_counter
