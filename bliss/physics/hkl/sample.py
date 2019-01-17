import numpy
import gi

gi.require_version("Hkl", "5.0")
from gi.repository import Hkl

from .common import *


class HklSample(object):
    UNIT = Hkl.UnitEnum.USER

    def __init__(self, geometry, detector, settings=None, sample_name="noname"):
        self._sample = Hkl.Sample.new(sample_name)
        self._geometry = geometry
        self._detector = detector
        self._ub_indexes = list()
        self._ub_calc_mode = "default"

        if settings is None:
            self._settings = dict()
        else:
            self._settings = settings
            self._init_settings()

    def _init_settings(self):
        name = self._settings.get("sample_name", None)
        if name is not None:
            self._sample.name_set(name)

        lattice = self._settings.get("sample_lattice", None)
        if lattice is not None:
            self.set_lattice(*lattice)
        calc_mode = self._settings.get("sample_calc_mode", None)
        reflections = self._settings.get("sample_reflections", None)
        if reflections is not None:
            self.set_reflections(reflections)
            if len(reflections) >= 2:
                if calc_mode == "busing_levy":
                    self.computeUB()
                elif calc_mode == "affine":
                    self.affine()
        if calc_mode == "manual":
            ubarray = self._settings.get("UB", None)
            if ubarray is None:
                self._settings["sample_calc_mode"] = "default"
            else:
                self.set_UB(ubarray)

    def get_sample(self):
        return self._sample

    def get_name(self):
        return self._sample.name_get()

    def set_name(self, name):
        self._sample.name_set(name)
        self._settings["sample_name"] = name

    def set_lattice(self, a, b, c, alpha, beta, gamma):
        lattice = self._sample.lattice_get()
        lattice.set(a, b, c, alpha, beta, gamma, self.UNIT)
        self._sample.lattice_set(lattice)
        self._settings["sample_lattice"] = (a, b, c, alpha, beta, gamma)

    def get_lattice(self):
        lattice = self._sample.lattice_get()
        (a, b, c, alpha, beta, gamma) = lattice.get(self.UNIT)
        return (a, b, c, alpha, beta, gamma)

    def get_reciprocal_lattice(self):
        lattice = self._sample.lattice_get()
        reciprocal = lattice.copy()
        lattice.reciprocal(reciprocal)
        (a, b, c, alpha, beta, gamma) = reciprocal.get(self.UNIT)
        return (a, b, c, alpha, beta, gamma)

    def get_UB(self):
        mat = self._sample.UB_get()
        arr = matrix_to_numpy(mat)
        return arr

    def set_UB(self, UB_array):
        mat = numpy_to_matrix(UB_array)
        self._sample.UB_set(mat)
        self._ub_calc_mode = "manual"
        self._settings["sample_calc_mode"] = "manual"
        self._settings["sample_UB"] = UB_array

    def get_U(self):
        mat = self._sample.U_get()
        arr = matrix_to_numpy(mat)
        return arr

    def set_U(self, U_array):
        mat = numpy_to_matrix(U_array)
        self._sample.U_set(mat)
        self._ub_calc_mode = "manual"

    def affine(self):
        self._sample.affine()
        self._ub_calc_mode = "affine"
        self._settings["sample_calc_mode"] = "affine"

    def add_one_reflection(self, hkl, pos=None, wl=None):
        (h, k, l) = hkl
        if pos is None and wl is None:
            use_geo = self._geometry
        else:
            use_geo = self._geometry.copy()
            if pos is not None:
                set_geometry_positions(use_geo, pos, self.UNIT)
            if wl is not None:
                use_geo.wavelength_set(wl, self.UNIT)
        self._sample.add_reflection(use_geo, self._detector, h, k, l)
        self.__save_reflections_2_settings()

    def set_one_reflection(self, idx, hkl, pos=None, wl=None):
        oneref = self.__get_ref_by_index(idx)
        (h, k, l) = hkl
        oneref.hkl_set(h, k, l)
        if pos is not None or wl is not None:
            use_geo = self._geometry.copy()
            if pos is not None:
                set_geometry_positions(use_geo, pos, self.UNIT)
            if wl is not None:
                use_geo.wavelength_set(wl, self.UNIT)
            oneref.geometry_set(use_geo)
        self.__save_reflections_2_settings()

    def get_one_reflection(self, idx):
        oneref = self.__get_ref_by_index(idx)
        return self.__get_ref_tuple(oneref)

    def get_reflections(self):
        refs = self._sample.reflections_get()
        allrefs = tuple()
        for oneref in refs:
            allrefs += (self.__get_ref_tuple(oneref),)
        return allrefs

    def set_reflections(self, allrefs):
        for ref in self._sample.reflections_get():
            self._sample.del_reflection(ref)
        for hkl, pos, wl in allrefs:
            self.add_one_reflection(hkl, pos, wl)
        self.__save_reflections_2_settings()

    def get_n_reflections(self):
        return len(self._sample.reflections_get())

    def __save_reflections_2_settings(self):
        self._settings["sample_reflections"] = self.get_reflections()

    def __get_ref_by_index(self, idx):
        refs = self._sample.reflections_get()
        try:
            oneref = refs[idx]
        except:
            raise ValueError("Invalid reflection index [{0}]".format(idx))
        return oneref

    def __get_ref_tuple(self, ref):
        (h, k, l) = ref.hkl_get()
        hkl_geo = ref.geometry_get()
        hkl_pos = get_geometry_positions(hkl_geo, self.UNIT)
        hkl_wl = hkl_geo.wavelength_get(self.UNIT)
        return ((h, k, l), hkl_pos, hkl_wl)

    def remove_one_reflection(self, idx):
        oneref = self.__get_ref_by_index(idx)
        self._sample.del_reflection(oneref)
        self.__save_reflections_2_settings()

    def remove_reflections(self):
        for ref in self._sample.reflections_get():
            self._sample.del_reflection(ref)
        self.__save_reflections_2_settings()

    def set_ref0(self, hkl, pos=None, wl=None):
        nref = self.get_n_reflections()
        if nref < 1:
            self.add_one_reflection(hkl, pos, wl)
        else:
            self.set_one_reflection(0, hkl, pos, wl)

    def get_ref0(self):
        return self.get_one_reflection(0)

    def set_ref1(self, hkl, pos=None, wl=None):
        nref = self.get_n_reflections()
        if nref < 1:
            raise ValueError("Define reflection 0 first")
        if nref < 2:
            self.add_one_reflection(hkl, pos, wl)
        else:
            self.set_one_reflection(1, hkl, pos, wl)

    def get_ref1(self):
        return self.get_one_reflection(1)

    def swap(self):
        self.swap_reflections(0, 1)

    def swap_reflections(self, idx1=0, idx2=1):
        (hkl1, pos1, wl1) = self.get_one_reflection(idx1)
        (hkl2, pos2, wl2) = self.get_one_reflection(idx2)
        self.set_one_reflection(idx1, hkl2, pos2, wl2)
        self.set_one_reflection(idx2, hkl1, pos1, wl1)

    def computeUB(self, idx1=0, idx2=1):
        ref1 = self.__get_ref_by_index(idx1)
        ref2 = self.__get_ref_by_index(idx2)
        self._sample.compute_UB_busing_levy(ref1, ref2)
        self._ub_indexes = [idx1, idx2]
        self._ub_calc_mode = "busing_levy"
        self._settings["sample_calc_mode"] = "busing_levy"

    def get_one_reflection_angles(self, idx1, idx2):
        ref1 = self.__get_ref_by_index(idx1)
        ref2 = self.__get_ref_by_index(idx2)
        meas = self._sample.get_reflection_measured_angle(ref1, ref2)
        theo = self._sample.get_reflection_theoretical_angle(ref1, ref2)
        return (meas, theo)

    def get_reflections_angles(self):
        refs = self._sample.reflections_get()
        nref = len(refs)
        meas = numpy.zeros(nref, nref)
        theo = numpy.zeros(nref, nref)
        for i, ref1 in enumerate(refs):
            for j, ref2 in enumerate(refs):
                if i != j:
                    meas[i, j] = self._sample.get_reflection_measured_angle(ref1, ref2)
                    theo[i, j] = self._sample.get_reflection_theoretical_angle(
                        ref1, ref2
                    )
        return (meas, theo)

    def info(self, mapnames=dict()):
        msg = "SAMPLE : {0}\n".format(self.get_name())
        msg += "LATTICE (lengths / angles):\n"
        msg += "         real space = {0:.4g} {1:.4g} {2:.4g} / {3:.4g} {4:.4g} {5:.4g}\n".format(
            *self.get_lattice()
        )
        msg += "   reciprocal space = {0:.4g} {1:.4g} {2:.4g} / {3:.4g} {4:.4g} {5:.4g}\n".format(
            *self.get_reciprocal_lattice()
        )
        msg += "\nUB ({0}):\n{1}\n".format(self._ub_calc_mode, str(self.get_UB()))
        refs = self.get_reflections()
        nref = len(refs)
        if not nref:
            msg += "\nREFLECTIONS : no reflection defined\n"
        else:
            axis_names = self._geometry.axis_names_get()
            axstr = " ".join(
                ["-{0}-".format(mapnames.get(name, name)) for name in axis_names]
            )
            msg += "\nREFLECTIONS (H K L {0} lambda):\n".format(axstr)
            for idx, ref in enumerate(refs):
                ((h, k, l), pos, wl) = ref
                posstr = " ".join(
                    ["{0:10.4f}".format(pos[name]) for name in axis_names]
                )
                msg += " [{0}] :  {1} {2} {3} {4} {5:g}\n".format(
                    idx, h, k, l, posstr, wl
                )
        return msg
