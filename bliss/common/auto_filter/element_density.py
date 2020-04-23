# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import math, numpy

from PyMca5.PyMcaPhysics.xrf import Elements


class ElementDensity:
    def __init__(self):
        self.__names = []
        self.__formules = []
        self.__ids = {}
        self.__last_material_name = ""

    def _get_material_id(self, name):
        """
        Return the material identifier for a given name
        """
        self.__last_material_name = name
        if name in self.__names:
            return self.__names.index(name)
        if name in self.__formules:
            return self.__formules.index(name)
        # one has to try to define a new element/compound
        # I should check if the name as it is exists in user and default directories
        if name in Elements.Element:
            # single element
            self.__names.append(Elements.Element[name]["name"])
            self.__formules.append(name)
            key = self.__formules.index(name)
            self.__ids[key] = Elements.getMaterialMassAttenuationCoefficients(name, 1)
            self.__ids[key]["density"] = Elements.Element[name]["density"]
            self.__ids[key]["energy"] = numpy.array(self.__ids[key]["energy"])
        else:
            # compound
            try:
                self.__names.append(name)
                self.__formules.append(name)
                matt = Elements.getMaterialMassAttenuationCoefficients(name, 1)
                key = self.__formules.index(name)
                self.__ids[key] = matt
                if self.__ids[key] == {}:
                    del self.__ids[key]
                    del self.__formules[key]
                    del self.__names[key]
                    key = -1
                else:
                    self.__ids[key]["density"] = Elements.Material[name]["Density"]
                    self.__ids[key]["energy"] = numpy.array(self.__ids[key]["energy"])
            except:
                key = -1
            if key == -1:
                raise RuntimeError(f"Cannot get ID for material {name}")
        return key

    def _get_formula(self, id):
        """
        Return the formula of the given material ID id
        """
        if id in self.__ids.keys():
            return self.__formules[id]
        else:
            raise RuntimeError(f"Cannot get formula for material ID {id}")

    def _get_name(self, id):
        """
        Return the material name of a given ID id
        """
        if id in self.__ids.keys():
            return self.__names[id]
        else:
            raise RuntimeError(f"Cannot get material name for ID {id}")

    def _get_density(self, id):
        """
        Return the material density for a given ID id
        """
        if id in self.__ids and "density" in self.__ids[id]:
            return self.__ids[id]["density"]
        else:
            raise RuntimeError(f"Cannot get density for material ID {id}")

    def _get_crosssection(self, id, energies):
        """
        Return the cross section for the given:
            element id
            list of energies (keV)
        """
        if id not in self.__ids.keys():
            raise RuntimeError(f"Invalid material ID {id}")

        if len(energies) == 0:
            return numpy.concatenate(
                (
                    self.__ids[id]["energy"],
                    self.__ids[id]["total"],
                    self.__ids[id]["photo"],
                    self.__ids[id]["coherent"],
                    self.__ids[id]["compton"],
                    self.__ids[id]["pair"],
                )
            )
        else:
            xcom_data = {}
            xcom_data.update(self.__ids[id])

            mydict = {}
            mydict["energy"] = []
            mydict["total"] = []
            mydict["photo"] = []
            mydict["coherent"] = []
            mydict["compton"] = []
            mydict["pair"] = []
            for ene in energies:
                i0 = numpy.max(numpy.nonzero((xcom_data["energy"] <= ene)))
                i1 = numpy.min(numpy.nonzero((xcom_data["energy"] >= ene)))
                if i1 == i0:
                    cohe = xcom_data["coherent"][i1]
                    comp = xcom_data["compton"][i1]
                    photo = xcom_data["photo"][i1]
                    pair = xcom_data["pair"][i1]
                else:
                    A = xcom_data["energy"][i0]
                    B = xcom_data["energy"][i1]
                    c2 = (ene - A) / (B - A)
                    c1 = (B - ene) / (B - A)

                    cohe = pow(
                        10.0,
                        c2 * numpy.log10(xcom_data["coherent"][i1])
                        + c1 * numpy.log10(xcom_data["coherent"][i0]),
                    )
                    comp = pow(
                        10.0,
                        c2 * numpy.log10(xcom_data["compton"][i1])
                        + c1 * numpy.log10(xcom_data["compton"][i0]),
                    )
                    photo = pow(
                        10.0,
                        c2 * numpy.log10(xcom_data["photo"][i1])
                        + c1 * numpy.log10(xcom_data["photo"][i0]),
                    )
                    if xcom_data["pair"][i1] > 0.0:
                        c2 = c2 * numpy.log10(xcom_data["pair"][i1])
                        if xcom_data["pair"][i0] > 0.0:
                            c1 = c1 * numpy.log10(xcom_data["pair"][i0])
                            pair = pow(10.0, c1 + c2)
                        else:
                            pair = 0.0
                    else:
                        pair = 0.0
                mydict["energy"].append(ene)
                mydict["coherent"].append(cohe)
                mydict["compton"].append(comp)
                mydict["photo"].append(photo)
                mydict["pair"].append(pair)
                mydict["total"].append((cohe + comp + photo + pair))
            return numpy.concatenate(
                (
                    mydict["energy"],
                    mydict["total"],
                    mydict["photo"],
                    mydict["coherent"],
                    mydict["compton"],
                    mydict["pair"],
                )
            )

    def get_density(self, material):
        """
        Return the material theoritical density in g/cm3
        """
        id = self._get_material_id(material)
        density = self._get_density(id)
        return density

    def get_crosssection(self, material, energy):
        """
        Return material cross-section at given energy
        """
        id = self._get_material_id(material)
        cs = self._get_crosssection(id, [energy])
        return cs[1]

    def get_transmission(self, material, thickness, energy, density=None):
        """
        Return material transmission for the given:
            thickness (mm)
            energy (kev)
            density (g/cm3) if given otherwise use the theoritical density
        """
        if density is None:
            density = self.get_density(material)
        cross = self.get_crosssection(material, energy)
        trans = math.exp(-cross * density * thickness * 0.1)
        return trans

    def get_calcdensity(self, material, thickness, transmission, energy):
        """
        Calculates apparent density to fit given thickness/transmission/energy
             thickness (mm)
             energy (kev)
        """
        cross = self.get_crosssection(material, energy)
        density = -math.log(transmission) / (cross * thickness * 0.1)
        return density

    def get_interpoledensity(
        self, material, thickness, transm0, ene0, transm1, ene1, energy
    ):
        """
        Interpolates apparent density to fit given thickness/transmission/energy
        Return apparent density at given energy
        """
        den0 = self.get_calcdensity(material, thickness, transm0, ene0)
        den1 = self.get_calcdensity(material, thickness, transm1, ene1)
        density = (den1 - den0) * (energy - ene0) / (ene1 - ene0) + den0
