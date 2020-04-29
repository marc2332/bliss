# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Class AutoFilterSetWheel serves to control the wheel filterset like model on ID10 
a motor driven wheel with up to 20 slots for attenuating the beam intensity.

Filters can be configured with only material and thickness then the density will be the theoric one
othewise one can set an density (g/cm3) or a pair of transmission(range [0-1]) / energy (keV).

Example of yml configuration files:

With NO density:
---------------

- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - name:Cu_0
      position: 0
      material: Cu
      thickness: 0
    - name:Cu_1
      position: 1
      material: Cu
      thickness: 0.04673608
    - name:Cu_2
      position: 2
      material: Cu
      thickness: 0.09415565
    - name:Cu_3
      position: 3
      material: Cu
      thickness: 0.14524267
    - name:Cu_4
      position: 4
      material: Cu
      thickness: 0.1911693
    - name:Cu_5
      position: 5
      material: Cu
      thickness: 0.24215921
    - name:Cu_6
      position: 6
      material: Cu
      thickness: 0.27220901
    - name:Cu_7
      position: 7
      material: Cu
      thickness: 0.3227842

With Density:
-------------
- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - name:Cu_0
      position: 0
      material: Cu
      thickness: 0
      density: 8.94

    - name:Mo_1
      position: 1
      material: Mo
      thickness: 0.055
      density: 10.22

With pairs transmission/energy:
------------------------------

- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - name:Ag_0
      position: 0
      material: Ag
      thickness: 0.1
      transmission: 0.173
      energy: 16

    - name:Ag_1
      position: 1
      material: Ag
      thickness: 0.2
      transmission: 0.0412
      energy: 16

"""

import math
import time
import numpy as np

from bliss.common.auto_filter.filterset import FilterSet


class FilterSet_Wheel(FilterSet):
    def __init__(self, name, config):
        self._config = config
        self._name = name

        # check some config
        self._rotation_axis = config.get("rotation_axis")

        # never forget to call grandmother !!!
        super().__init__(name, config)

        self._positions = []
        for filter in self._filters:
            self._positions.append(filter["position"])

    def __info__(self):
        info_list = []
        info_list.append(f"Filterset Wheel: {self._name}")

        info_list.append(f" - Rotation axis: {self._rotation_axis.name}")
        info_list.append(
            f" - Idx   Pos. Mat. Thickness    Transm. @ {self._energy_setting:.5g} keV:"
        )
        info_list.append("   -------------------------------------------------")
        for filter in self._filters:
            idx = self._filters.index(filter)
            info_list.append(
                f"   {idx:<4}  {filter['position']:<4} {filter['material']:<4} {filter['thickness']:10.8f}   {filter['transmission_calc']:.5g}"
            )
        return "\n".join(info_list) + "\n" + super().__info__()

    # --------------------------------------------------------------
    # Here start the mother class overloaded methods to create
    # a new filterset
    # --------------------------------------------------------------
    def decr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to increment the filter level
        value -- measure data
        max_count_rate -- maximum authorize value
        """
        print(f"{value} {min_count_rate} {max_count_rate}")

    def incr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to increment the filter level
        value -- measure data
        max_count_rate -- maximum authorize value
        """
        print(f"{value} {min_count_rate} {max_count_rate}")

    def set_filter(self, new_filter):
        """
        Set the new filter, for a wheel it correspond to a
        precise axis position
        """
        if new_filter not in range(len(self._filters)):
            raise ValueError(
                f"Wrong filter value {new_filter} range is [0-{self._nb_filters-1}]"
            )
        self._rotation_axis.move(self._filters[new_filter]["position"])

    def get_filter(self):
        """
        Return the wheel filter and the transmission.
        (None,None) is return if the axis position does not correspond to the 
        defined positions
        """
        position = self._rotation_axis.position
        if position in self._positions:
            filt = self._positions.index(position)
            return filt
        else:
            return None

    def get_transmission(self):
        """
        Return the current effective tranmission
        """
        filt = self.get_filter()
        if filt is not None:
            trans = self._filters[filt]["transmission_calc"]
        else:
            trans = None
        return trans

    def build_filterset(self):
        """
        Build pattern and transmission arrays.
        A filterset, like Wago, is made of 4 real filters 
        which can be combined to produce 15 patterns and transmissions.
        A filtersets like a wheel just provides 20 real filters and exactly
        the same amount of patterns and transmissions.
        """

        p = []
        t = []
        for filter in self._filters:
            p.append(filter["position"])
            t.append(filter["transmission_calc"])
        self._fpattern = np.array(p, dtype=np.int)
        self._ftransm = np.array(t)

        return len(self._fpattern)
