
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
from bliss.common.logtools import *
from element_density import ElementDensity


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

        self._fpattern = None
        self._ftransm = None
        self._filter_data = None
        self._min_cntrate = 0.
        self._max_cntrate = 0.
        self._nb_filters = 0

        # good element density module
        self._elt = ElementDensity()

        self._filters = config.get("filters")
        if not len(self._filters):
            raise RuntimeError("Filter list is empty")

        self._nb_filters = len(self._filters)

        # ask for the calculation of the apparent density and
        # and a first transmission of the filters
        self._calc_densities()

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

    def _calc_transmissions(self, energy):
        """
        Calculate the transmission factors for the filters for the given energy
        """

        for filter in self._filters:
            filter["transmission_calc"] = self._elt.get_transmission(
                filter["material"], filter["thickness"], energy, filter["density_calc"]
            )
        # save in setting the last energy
        self._energy_setting = energy

    def _calc_absorption_table(self):
        """
        This function regenerate the absorption table, which will be used to 
        apply the best absorption to fit with the count-rate range
        """

        log_info(self, "Regenerating absorption table")

        self._nb_filtset = self.build_filterset()

        min_trans = np.sqrt(self._min_cntrate / self._max_cntrate)
        max_trans = np.sqrt(min_trans)

        # the optimum count rate
        opt_cntrate = max_trans * self._max_cntrate

        log_info(self, f"min. transmission: {min_trans}")
        log_info(self, f"max. transmission: {max_trans}")
        log_info(self, f"opt. count rate: {opt_cntrate}")
        log_info(self, f"nb. filters: {self._nb_filters}")
        log_info(self, f"nb. filtset: {self._nb_filtset}")

        # Ok, the tricky loop to reduce the number of possible patterns according
        # to the current min. and max. transmission
        # Thanks to P.Fajardo, code copied for autof.mac SPEC macro set
        # It selects select only the patterns (fiterset)which fit with the transmission
        # range [min_trans,max_trans]

        d = 0
        nf = self._nb_filters
        for f in range(nf):
            s = self._ftransm[f:nf].argmax() + f
            pattern = self._fpattern[s]
            transm = self._ftransm[s]

            if transm == 0:
                break
            if s != f:
                self._fpattern[s] = self._fpattern[f]
                self._ftransm[s] = self._ftransm[f]
            if d == 0:
                pass
            elif d == 1:
                if (transm / self._ftransm[d - 1]) > max_trans:
                    continue
            else:
                if (transm / self._ftransm[d - 2]) > min_trans:
                    d -= 1
                elif (transm / self._ftransm[d - 1]) > max_trans:
                    continue
            if d != s:
                self._fpattern[d] = pattern
                self._ftransm[d] = transm

            d += 1

        # update filter number to the reduced one
        self._nb_filtset = nfiltset = d
        log_info(self, f"New nb. filtset: {self._nb_filtset}")

        # Now calculate the absorption / deadtime data
        # array of nfilters columns and rows of:
        #  - [pattern, transmission, max_cntrate, opt_cntrate, min_cntrate]
        #
        self._filter_data = np.zeros([nfiltset, 5])
        data = self._filter_data
        data[0:nfiltset, 0] = self._fpattern[0:nfiltset]
        data[0:nfiltset, 1] = self._ftransm[0:nfiltset]

        # a quality will be calculted, 100% means all above retained patterns are useful
        self._quality = nfiltset
        for f in range(nfiltset):
            data[f, 2] = self._max_cntrate / data[f, 1]
            if f == 0:
                data[f, 3] = 0
                data[f, 4] = 0
            else:
                data[f, 3] = opt_cntrate / data[f - 1, 1]
                data[f, 4] = self._min_cntrate / data[f, 1]
                if data[f, 4] > data[f, 3]:
                    data[f, 4] = data[f, 3]
                    self._quality -= 1
        self._quality = 100 * self._quality / nfiltset
        log_info(self, f"Finally quality is {self._quality}")

    def update_countrate_range(self, min_count_rate, max_count_rate):
        """
        update the countrate range, suppose to be called by the AutoFilter class
        which has the range set from its config.
        Then trig a first calculation of data from the current energy
        """
        self._min_cntrate = min_count_rate
        self._max_cntrate = max_count_rate

        self.energy = self._energy_setting

    @property
    def energy(self):
        return self._energy_setting

    @energy.setter
    def energy(self, new_energy):
        # each time the energy change effective transmission and
        # a new absorption table are calculated
        log_info(self, f"Updating the energy {new_energy} keV")

        self._calc_transmissions(new_energy)
        self._calc_absorption_table()

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

    def build_filterset(self):
        """
        Build pattern and transmission arrays.
        A filterset, like Wago, is made of 4 real filters 
        which can be combined to produce 15 patterns and transmissions.
        A filtersets like a wheel just provides 20 real filters and exactly
        the same amount of patterns and transmissions.
        Return the total number of effective filter combinations (filtset)
        """
        raise RuntimeError("Please override this method")
        return 0
