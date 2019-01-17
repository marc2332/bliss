
from .diff_base import Diffractometer


class DiffE4CH(Diffractometer):

    PSEUDOS_FMT = """\
H K L = {pos[hkl_h]:f} {pos[hkl_k]:f} {pos[hkl_l]:f}
Alpha = {pos[incidence_incidence]:.5g}  Beta = {pos[emergence_emergence]:.5g}  Azimuth = {pos[psi_psi]:.5g}
"""

    def show(self):
        print(("Four-Circle Geometry, HKL mode [{0}]".format(self.hklmode)))
        if len(self.frozen_angles_names):
            if len(self.frozen_angles):
                for name, value in self.frozen_angles.items():
                    print("Frozen {0:s} = {1:.4f}".format(name, value))
            else:
                print("No angles frozen yet.")
        if self.hklmode == "psi_constant":
            print("Constant psi = {0:.4f}".format(self.psi_constant))
        if self.sample.get_n_reflections() < 1:
            print("\nPrimary reflection not yet defined.")
        else:
            (hkl, pos, wl) = self.sample.get_ref0()
            hstr = ["{0:s}".format(self._motor_names[name]) for name in self.axis_names]
            pstr = ["{0:.4f}".format(pos[name]) for name in self.axis_names]
            print(("\nPrimary Reflection (at lambda {0:.4f}):".format(wl)))
            print(("{0:>26s} = {1}".format(" ".join(hstr), " ".join(pstr))))
            print(("{0:>26s} = {1} {2} {3}".format("H K L", *hkl)))
        if self.sample.get_n_reflections() < 2:
            print("\nSecondary reflection not yet defined.")
        else:
            (hkl, pos, wl) = self.sample.get_ref1()
            hstr = ["{0:s}".format(self._motor_names[name]) for name in self.axis_names]
            pstr = ["{0:.4f}".format(pos[name]) for name in self.axis_names]
            print(("\nSecondary Reflection (at lambda {0:.4f}):".format(wl)))
            print(("{0:>26s} = {1}".format(" ".join(hstr), " ".join(pstr))))
            print(("{0:>26s} = {1} {2} {3}".format("H K L", *hkl)))
        print("\nLattice Constants (lengths / angles):")
        print(
            (
                "{0:>26s} = {1:.3f} {2:.3f} {3:.3f} / {4:.3f} {5:.3f} {6:.3f}".format(
                    "real space", *self.sample.get_lattice()
                )
            )
        )
        print(
            (
                "{0:>26s} = {1:.3f} {2:.3f} {3:.3f} / {4:.3f} {5:.3f} {6:.3f}".format(
                    "reciprocal space", *self.sample.get_reciprocal_lattice()
                )
            )
        )
        print("\nAzimuthal reference:")
        print(("{0:>26s} = {1} {2} {3}".format("H K L", *self.azimuth_ref)))
        print("Normal reference:")
        print(("{0:>26s} = {1} {2} {3}".format("H K L", *self.normal_ref)))
        print(
            "\nLambda = {0:.5f}  Energy = {1:.3f} keV".format(
                self.wavelength, self.energy
            )
        )

        # --- motor geometry limits to add

    def pseudo_pos_2_str(self, pos_dict):
        return self.PSEUDOS_FMT.format(pos=pos_dict)

    @property
    def azimuth_ref(self):
        azi_vals = self._geometry.get_mode_pars("psi", "psi")
        return (azi_vals["h2"], azi_vals["k2"], azi_vals["l2"])

    @azimuth_ref.setter
    def azimuth_ref(self, vals):
        if len(vals) != 3:
            raise ValueError("Give (h,k,l) to define azimuth reference")
        azi_vals = dict(list(zip(("h2", "k2", "l2"), vals)))
        self._geometry.set_mode_pars("psi", "psi", azi_vals)
        self._geometry.set_mode_pars("hkl", "psi_constant", azi_vals)
        self._calc_geo()

    @property
    def normal_ref(self):
        norm_vals = self._geometry.get_mode_pars("incidence", "incidence")
        return (norm_vals["x"], norm_vals["y"], norm_vals["z"])

    @normal_ref.setter
    def normal_ref(self, vals):
        if len(vals) != 3:
            raise ValueError("Give (x,y,z) to define normal reference")
        norm_vals = dict(list(zip(("x", "y", "z"), vals)))
        self._geometry.set_mode_pars("incidence", "incidence", norm_vals)
        self._geometry.set_mode_pars("emergence", "emergence", norm_vals)
        self._calc_geo()

    @property
    def psi_constant(self):
        psi_vals = self._geometry.get_mode_pars("hkl", "psi_constant")
        return psi_vals["psi"]

    @psi_constant.setter
    def psi_constant(self, value):
        psi_vals = self._geometry.get_mode_pars("hkl", "psi_constant")
        psi_vals["psi"] = value
        self._geometry.set_mode_pars("hkl", "psi_constant", psi_vals)


class DiffE4CV(DiffE4CH):

    PSEUDOS_FMT = """\
H K L = {pos[hkl_h]:f} {pos[hkl_k]:f} {pos[hkl_l]:f}
Alpha = {pos[incidence_incidence]:.5g}  Beta = _._  Azimuth = {pos[psi_psi]:.5g}
"""

    @property
    def normal_ref(self):
        norm_vals = self._geometry.get_mode_pars("incidence", "incidence")
        return (norm_vals["x"], norm_vals["y"], norm_vals["z"])

    @normal_ref.setter
    def normal_ref(self, vals):
        if len(vals) != 3:
            raise ValueError("Give (x,y,z) to define normal reference")
        norm_vals = dict(list(zip(("x", "y", "z"), vals)))
        self._geometry.set_mode_pars("incidence", "incidence", norm_vals)
        # self._geometry.set_mode_pars("emergence", "emergence", norm_vals)
