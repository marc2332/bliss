
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Master class for filterset.

The child class must provide  definition for the filters with name/position/material/thickness.
Optionnally one can add either a density or a pair transmission/energy.
the units are :
 - thickness [mm]
 - density [g/cm3]
 - transmission [0. - 1.]
 - energy [keV]

Some examples of yml config:
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

To Write a new filterset controller one should override these methods:
  * decr_filter()
  * incr_filter()
  * set_filter()
  * get_filter()
  * get_transmission()
  * build_filterset()
"""
import numpy as np
from tabulate import tabulate

from bliss.config.beacon_object import BeaconObject


class FilterSet(BeaconObject):
    """
    This is mother class which should be inherited by any new filterset controller.
    The are some mandatory methods/properties to be overrided
    """

    _energy_setting = BeaconObject.property_setting(
        "_energy_setting",
        default=10.0,
        must_be_in_config=False,
        doc="The last set energy (keV)",
    )

    def __init__(self, name, config):
        super().__init__(config, share_hardware=False)

        # good element density module
        self._elt = ElementDensity()

        self._filters = config.get("filters")
        if not len(self._filters):
            raise RuntimeError("Filter list is empty")

        self._nb_filters = len(self._filters)
        self._positions = []
        for filter in self._filters:
            self._positions.append(filter["position"])

        # ask for the calculation of the apparent density and
        # and a first transmission of the filters
        self._calc_densities()
        self.calc_transmissions(self._energy_setting)

    def __info__(self):
        info_str = f"\nActive filter is {self.filter}, transmission = {self.transmission:.5g} @ {self.energy:.5g} keV"
        return info_str

    def info_table(self):
        """
        Return the informatio regarding the absorption table, the remaining effective filters 
        which will be used during a scan.
        """
        table_info = []

        for filt in self._abs_table:
            table_info.append(list(filt))
        info = str(
            tabulate(
                table_info,
                headers=[
                    "Idx",
                    "Transm.",
                    "Max.cntrate",
                    "Opti.cntrate",
                    "Min.cntrate",
                ],
                floatfmt=".4g",
                numalign="left",
            )
        )
        info += "\n"
        return info

    def _calc_densities(self):
        """
        Calculate the apparent density of the filters
        Density can be read from config,by element_density module,
        or interpolated from pairs of transmission/energy set in config
        """

        for filter in self._filters:
            if "density" in filter:
                filter["density_calc"] = filter["density"]
            else:
                filter["density_calc"] = filter["density"] = self._elt.get_density(
                    filter["material"]
                )
            if "transmission" in filter:
                if not "energy" in filter:
                    raise ValueError(
                        f"filter {filter['name']} has transmission but missing the corresponding energy"
                    )
                else:
                    filter["density_calc"] = self._elt.get_calcdensity(
                        filter["material"],
                        filter["thickness"],
                        filter["transmission"],
                        filter["energy"],
                    )

    def calc_transmissions(self, energy):
        """
        Calculate the transmission factors for the filters for the given energy
        """

        for filter in self._filters:
            filter["transmission_calc"] = self._elt.get_transmission(
                filter["material"], filter["thickness"], energy, filter["density_calc"]
            )
        # save in setting the last energy
        self._energy_setting = energy

    @property
    def energy(self):
        return self._energy_setting

    @energy.setter
    def energy(self, new_energy):
        self.calc_transmissions(new_energy)

    @property
    def filter(self):
        """
        setter/getter for the filter
        """
        return self.get_filter()

    @filter.setter
    def filter(self, new_filter):
        self.set_filter(new_filter)

    @property
    def transmission(self):
        """
        Return the transmission factor of the current filter
        """
        return self.get_transmission()

    # ------------------------------------------------------------
    # Here start the methods to be overrided by the filterset
    # ------------------------------------------------------------
    def decr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to increment the filter level
        value -- measure data
        max_count_rate -- maximum authorize value
        """
        raise RuntimeError("Please override this method")

    def incr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to increment the filter level
        value -- measure data
        max_count_rate -- maximum authorize value
        """
        raise RuntimeError("Please override this method")

    def set_filter(self, new_filter):
        """
        Set the new filter
        """
        raise RuntimeError("Please override this method")

    def get_filter(self):
        """
        Return the current filter and the transmission.
        (None,None) is return if filter position is undefined
        """
        raise RuntimeError("Please override this method")

    def get_transmission(self):
        """
        Return the current effective tranmission
        """
        raise RuntimeError("Please override this method")
