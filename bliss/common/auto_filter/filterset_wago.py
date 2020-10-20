# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Class FilterSet_Wago serves to control the DEG (former ISG) Wago filterset. 
Pneumatic system is driving 4 slots for attenuating the beam intensity.

Filters can be configured with only material and thickness then the density will be the theoric one
othewise one can set an density (g/cm3) or a pair of transmission(range [0-1]) / energy (keV).

Example of yml configuration files:

With NO density:
---------------

- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Cu
      thickness: 0
    - position: 1
      material: Cu
      thickness: 0.04673608
    - position: 2
      material: Cu
      thickness: 0.09415565
    - position: 3
      material: Cu
      thickness: 0.14524267

With Density:
-------------
- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Cu
      thickness: 0
      density: 8.94
    - position: 1
      material: Mo
      thickness: 0.055
      density: 10.22

With pairs transmission/energy:
------------------------------

- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Ag
      thickness: 0.1
      transmission: 0.173
      energy: 16

    - position: 1
      material: Ag
      thickness: 0.2
      transmission: 0.0412
      energy: 16

"""

import numpy as np
from gevent import sleep

from bliss.common.auto_filter.filterset import FilterSet


class FilterSet_Wago(FilterSet):
    def __init__(self, name, config):
        self._config = config
        self._name = name

        # check some config
        self._wago = config.get("wago_controller")
        self._wago_cmd = config.get("wago_cmd")
        self._wago_status = config.get("wago_status")

        # optional config
        self._inverted = config.get("inverted", False)
        self._overlap_time = config.get("overlap_time", 0)
        self._settle_time = config.get("settle_time", 0)

        # never forget to call grandmother !!!
        super().__init__(name, config)

        self._positions = []
        for filter in self._filters:
            self._positions.append(filter["position"])

    def __info__(self):
        info_list = []
        info_list.append(f"Filterset Wago: {self._name}")

        info_list.append(f" - Wago: {self._wago.name}")
        info_list.append(
            f" - Idx   Mat. Thickness    Transm. @ {self._last_energy:.5g} keV:"
        )
        info_list.append("   ---------------------------------------------")
        for filter in self._config_filters:
            idx = self._config_filters.index(filter)
            info_list.append(
                f"   {idx:<4}  {filter['material']:<4} {filter['thickness']:10.8f}   {filter['transmission_calc']:.5g}"
            )

        info_list.append("\n\n Combined filter set:")
        info_list.append(f" - Idx  Transm. @ {self._last_energy:.5g} keV:")
        info_list.append("   --------------------------")
        for filter in self._filters:
            idx = self._filters.index(filter)
            info_list.append(f"   {idx:<4} {filter['transmission_calc']:.5g}")

        return "\n".join(info_list) + "\n" + super().__info__()

    # --------------------------------------------------------------
    # Here start the mother class overloaded methods to create
    # a new filterset
    # --------------------------------------------------------------

    def set_filter(self, filter_id):
        """
        Set the new filter, for the wago filter_id is a mask
        """
        if filter_id < 0 or filter_id > self._filtmask:
            raise ValueError(
                f"Wrong filter value {filter_id} range is [0-{self._filtmask}]"
            )

        nbits = self._config_nb_filters

        # do not let 0 filter to be set otherwise detector
        # can be damaged, so first set on new filters by
        # making a logic OR between previous and new mask

        mask = self.get_filter() | filter_id
        mask = (self._filtmask - mask) if self._inverted else mask
        wmask = [int(x) for x in f"{mask:0{nbits}b}"]
        self._wago.set(self._wago_cmd, wmask)
        sleep(self._overlap_time)

        mask = (self._filtmask - filter_id) if self._inverted else filter_id
        wmask = [int(x) for x in f"{mask:0{nbits}b}"]
        wmask.reverse()
        self._wago.set(self._wago_cmd, wmask)
        sleep(self._settle_time)

    def get_filter(self):
        """
        Return the wago filter mask.
        """
        mask = 0
        val = self._wago.get(self._wago_status)
        for f in range(self._config_nb_filters):
            mask += int(val[f]) << f
        return mask

    def get_transmission(self, filter_id=None):
        """
        Return the tranmission of filter filter_id
        if None, return the curent filter transmission
        """
        if not filter_id:
            filt = self.get_filter()
        else:
            filt = filter_id
        if filt is not None:

            trans = self._filters[filt]["transmission_calc"]
        else:
            trans = None
        return trans

    def build_filterset(self):
        """
        Build pattern (index here)  and transmission arrays.
        A filterset, like Wago, is made of 4 real filters (or more)
        which can be combined to produce 15 patterns and transmissions.
        A filtersets like a wheel just provides 20 real filters and exactly
        the same amount of patterns and transmissions.
        """

        # make a mask in case of inverted filterset
        self._filtmask = pow(2, self._config_nb_filters) - 1

        nbits = self._config_nb_filters
        # filter id 0 is no filter
        p = [0]
        t = [1.]
        self._built_filters = [{"position": 0, "transmission_calc": 1.}]

        for filt_id in range(1, self._filtmask + 1):
            # store just the index of the filters as the possible pattern
            p.append(filt_id)
            mask = [int(x) for x in f"{filt_id:0{nbits}b}"]
            mask.reverse()
            trans = 1.

            # TODO : optimize to loop only on the effective bits
            for f in range(nbits):
                if int(mask[f]) == 1:
                    trans *= self._config_filters[f]["transmission_calc"]

            t.append(trans)
            self._built_filters.append(
                {"position": filt_id, "transmission_calc": trans}
            )
        self._fpattern = np.array(p, dtype=np.int)
        self._ftransm = np.array(t)
        return len(self._fpattern)

    def get_filters(self):
        """
        Return the list of the public filters, a list of dictionnary items with at least:
        - position
        - transmission_calc
        """
        return self._built_filters
