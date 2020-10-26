# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2010 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
from bliss.icat.definitions import Definitions
from os.path import commonprefix
from bliss.common.protocols import IcatPublisher
from collections.abc import MutableSequence


class ICATmeta:
    def __init__(self, name, config):
        self.config = config
        self.mapping = config.get("mapping", {})
        self.objects = config.get("objects", {})
        self.positioners = config.get("positioners", {})
        self.definitions = Definitions()

        for key, obj in self.objects.items():
            if not isinstance(obj, IcatPublisher):
                raise RuntimeError(
                    f"{obj.name} ({key}) is not a valid metadata publisher!"
                )

    def get_metadata(self):
        res = dict()
        for key, value in self.mapping.items():
            if isinstance(value, MutableSequence):
                res[key] = ""
                for sub_value in value:
                    res[key] += str(sub_value) + " "
            else:
                res[key] = str(value)

        instrumentation = self.definitions.instrumentation._asdict()
        for key, device in self.objects.items():
            assert key in instrumentation, f"{key} is not a known icat field group"
            assert hasattr(
                device, "metadata"
            ), f"{device.name} has no metadata function"
            prefix = commonprefix(list(instrumentation[key].fields)).strip("_")
            # have to deal with cases where there is no tailing `_` in the prefix
            # e.g. attenuator positions
            obj_meta = device.metadata()
            for icat_key in instrumentation[key].fields:
                obj_key = icat_key.split(prefix)[-1].strip("_")
                if obj_key in obj_meta:
                    res[icat_key] = str(obj_meta[obj_key])

        positioners = self.definitions.positioners._asdict()
        for key, pos_list in self.positioners.items():
            if not isinstance(pos_list, MutableSequence):
                pos_list = [pos_list]

            assert key in positioners, f"{key} not a known positioner group in icat"

            icat_name = [x for x in positioners[key].fields if "_name" in x][0]
            icat_value = [x for x in positioners[key].fields if "_value" in x][0]
            res[icat_name] = " ".join([x.name for x in pos_list])
            res[icat_value] = " ".join([str(x.position) for x in pos_list])

        return res
