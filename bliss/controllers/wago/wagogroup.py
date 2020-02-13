# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import collections

from tabulate import tabulate

from bliss.controllers.counter import counter_namespace, SamplingCounterController
from bliss.common.utils import add_property, merge, flatten
from bliss.controllers.wago.wago import get_module_info


class WagoGroup(SamplingCounterController):
    """ The wago group class
    """

    def __init__(self, name, config_tree):
        """
        wago:
            - name: wcid10a
              logical_keys: filt1, filt2
            - name: wcid10b
        """

        super().__init__(name=name)

        self._wagos = config_tree.get("wago", [])
        self._wago4key = {}
        self.logical_keys = []
        self.cnt_names = []

        for w in self._wagos:
            wago = w["name"]
            try:
                logical_keys = [s.strip() for s in w["logical_keys"].split(",")]
            except AttributeError:
                logical_keys = list(wago.modules_config.logical_keys)

            for key in logical_keys:
                if key not in wago.modules_config.logical_keys:
                    raise ValueError(
                        f"Logical name '{key}' does not exist in wago '{wago.name}'"
                    )

                if key in self.logical_keys:
                    raise ValueError(
                        f"Duplicate logical name '{key}' in wago group '{self.name}'"
                    )

                self.logical_keys.append(key)
                self._wago4key[key] = wago
                if hasattr(wago, key):
                    add_property(self, key, getattr(wago, key))
                    self.cnt_names.append(key)

        # global_map.register(
        #     self,
        #     parents_list=["wago"],
        #     children_list=[self.controller],
        #     tag=f"Wago({self.name})",
        # )

    def __info__(self):
        tab = [["logical device", "current value", "wago name", "description"]]
        try:
            values = self.get(*self.logical_keys, flat=True)
        except Exception:
            values = [None] * len(self.logical_keys)

        organized_values = []
        iter_val = iter(values)
        for key in self.logical_keys:
            modules_config = self._wago4key[key].modules_config
            for n_ch, ch in modules_config.read_table[key].items():
                wago_name = self._wago4key[key].name
                description = ch["info"].description
                if len(organized_values):
                    if (
                        organized_values[-1][0] == key
                        and organized_values[-1][3] == description
                    ):
                        # if modules belows to the same logical_device and module_type
                        # consider them as one
                        organized_values[-1][2].append(next(iter_val))
                        continue

                organized_values.append(
                    (key, n_ch, [next(iter_val)], description, wago_name)
                )

        for key, n_ch, values, description, wago_name in organized_values:
            tab.append([key, values, wago_name, description])

        repr_ = tabulate(tab, headers="firstrow", stralign="center")

        return repr_

    def set(self, *args, **kwargs):
        """Set one or more logical_devices
        Args should be list or pairs: channel_name, value
        or a list with channel_name, val1, val2, ..., valn
        or a combination of the two
        """
        channels_to_write = []
        for x in args:
            if type(x) in (bytes, str):
                # channel name
                current_list = [str(x)]
                channels_to_write.append(current_list)
            else:
                # value
                current_list.append(x)

        for wago in set(self._wago4key.values()):
            wago_args = merge(
                [x for x in channels_to_write if self._wago4key[x[0]] == wago]
            )
            if wago_args:
                wago.set(*wago_args, **kwargs)

    def get(self, *args, **kwargs):
        """Read one or more values from channels
        Args:
            *channel_names (list): list of channels to be read
            convert_values (bool): default=True converts from raw reading to meaningful values
            flat (bool):           default=True, if false: return a list item per channel

        Returns:
            (list): channel values
        """
        flat = kwargs.get("flat", True)
        wago_keys = collections.defaultdict(list)

        # sort keys per wago
        for key in args:
            wago_keys[self._wago4key[key]].append(key)

        # make one call to wago.get() per wago, without flatten list
        kwargs["flat"] = False
        wago_results = {
            wago: wago.get(*wago_keys[wago], **kwargs) for wago in wago_keys
        }

        # put results together in a dict(key -> result)
        results = dict(zip(merge(wago_keys.values()), merge(wago_results.values())))

        ret = [results[key] for key in args]

        if not flat:
            return ret

        if not ret:
            return None
        if len(ret) == 1:
            return ret[0]
        else:
            return flatten(ret)

    @property
    def counters(self):
        """Get the list of the configured counters
        Returns:
            (list): list of the configured counter objects
        """
        counters_list = []
        for cnt_name in self.cnt_names:
            counters_list.append(getattr(self, cnt_name))
        return counter_namespace(counters_list)

    def read_all(self, *counters):
        """Read all the counters
        Args:
            *counters (list): names of counters to be read
        Returns:
            (list): read values from counters
        """
        cnt_names = [cnt.name.replace(self.name + ".", "") for cnt in counters]
        result = self.get(*cnt_names)
        return result if isinstance(result, list) else [result]
