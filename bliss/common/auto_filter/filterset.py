
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
from .element_density import ElementDensity


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

        # Some data and caches
        self._fpattern = None
        self._ftransm = None
        self._abs_table = None
        self._min_cntrate = 0.
        self._max_cntrate = 0.
        self._nb_filters = 0
        self._curr_idx = -1
        self._backidx = -1
        self._back = True

        # good element density module
        self._elt = ElementDensity()

        self._filters = config.get("filters")
        if not len(self._filters):
            raise RuntimeError("Filter list is empty")

        self._nb_filters = len(self._filters)

        self.initialize()

    def initialize(self):
        """
        Initialize filter apparent densities and transmissions
        """
        self._calc_densities()
        self._calc_transmissions(self._energy_setting)

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
        self._abs_table = np.zeros([nfiltset, 5])
        data = self._abs_table
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

    def sync(self, min_count_rate, max_count_rate, energy, back):
        """
        Update the absorption table (_abs_table) using the new cntrate 
        range and the new energy.
        Check if the current filter is in the new table otherwise
        change it to the closest one.
        """
        self._min_cntrate = min_count_rate
        self._max_cntrate = max_count_rate
        self._back = back

        # each time the energy change effective transmission and
        # a new absorption table are calculated

        log_info(self, f"Updating the energy {energy} keV")
        self._calc_transmissions(energy)
        self._calc_absorption_table()

        # In case that the current filter is not in the abs. table
        # change to the closest one

        idx = self._read_filteridx()
        # _abs_table is a numpy array of float, so convert filter id to integer
        curr_filtid = int(self._abs_table[self._curr_idx, 0])
        if idx == -1:
            # of need to change with the closest filter
            # the new filter index is already stored in the cache attr. _curr_idx
            self.set_filter(curr_filtid)

        # Save filter index if needed
        if self._back:
            self._backid = curr_filtid

    def _read_filteridx(self):
        """
        Return current filter index
        If current filter is not in table, find the closest one in term of transmission
        Return -1 if the filter need to be changed and the new filter is stored in 
        self._curr_idx for the calling function
        """

        filtid = self.get_filter()
        curridx = self._curr_idx
        currid = int(self._abs_table[curridx, 0])

        log_info(self, f"Current filter id is {filtid}")
        if currid == filtid:
            return curridx

        trans = self.get_transmission(filtid)
        currtrans = 0
        nfiltset = self._nb_filtset

        found = False
        data = self._abs_table
        for idx in range(nfiltset):
            if filtid == int(data[idx, 0]):
                self._curr_idx = idx
                return idx
            trsm = data[idx, 1]
            if trsm <= trans and trsm > currtrans:
                currtrans = trsm
                curridx = idx
                found = True

        if not found:
            # be safe set the absorptionest filter
            curridx = nfiltset - 1

        log_info(self, f"Closest filter index is {curridx}")
        # put new
        self._curr_idx = curridx
        # return -1 means the filter must be changed
        return -1

    @property
    def energy(self):
        return self._energy_setting

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

    def set_filter(self, filter_id):
        """
        Set the new filter
        """
        raise RuntimeError("Please override this method")

    def get_filter(self):
        """
        Return the current filter index
        otherwise none is returned
        """
        raise RuntimeError("Please override this method")

    def get_transmission(self, filter_id=None):
        """
        Return the tranmission of filter 
        if None, return the curent filter transmission
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
