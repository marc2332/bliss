import types
import numpy
import tabulate
from six import print_
from bliss.physics.hkl.geometry import HklGeometry
from bliss.config.settings import HashObjSetting
from bliss.common.motor_group import Group as MotorGroup
from bliss.common.cleanup import error_cleanup
from gevent import sleep

__CURR_DIFF = None
__ALL_DIFF = dict()


def get_current_diffractometer():
    global __CURR_DIFF
    if __CURR_DIFF is None:
        try:
            __CURR_DIFF = list(__ALL_DIFF.values())[0]
        except:
            raise ValueError("No diffractometers defined.")
    return __CURR_DIFF


def register_diffractometer(name, obj):
    global __ALL_DIFF, __CURR_DIFF
    __ALL_DIFF[name] = obj
    if __CURR_DIFF is None:
        __CURR_DIFF = obj


def set_current_diffractometer(name_or_obj):
    global __CURR_DIFF
    if isinstance(name_or_obj, Diffractometer):
        obj = __ALL_DIFF.get(name_or_obj.name, None)
    else:
        obj = __ALL_DIFF.get(name_or_obj, None)
    if obj is None:
        raise ValueError("No diffractometer registered with name [{0}]".format(name))
    __CURR_DIFF = obj


def get_diffractometer_list():
    return list(__ALL_DIFF.keys())


def pprint_diff_settings(name):
    settings = dict(HashObjSetting(name))
    for key in [key for key in settings.keys() if key.startswith("sample_")]:
        val = settings.pop(key)
        if key == "sample_reflections":
            print("* {0} :".format(key))
            for ref in val:
                print("    - {0}".format(ref))
        else:
            print("* {0} : {1}".format(key, val))
    for key in [key for key in settings.keys() if key.endswith("_limits")]:
        print("* {0} : {1}".format(key, settings.pop(key)))
    for key in [key for key in settings.keys() if key.endswith("_mode")]:
        print("* {0} : {1}".format(key, settings.pop(key)))
    for key in [key for key in settings.keys() if key.endswith("_pars")]:
        print("* {0} : {1}".format(key, settings.pop(key)))
    for key, val in settings.items():
        print("* {0} : {1}".format(key, val))


def remove_diff_settings(name, *keys):
    settings = HashObjSetting(name)
    if not len(keys):
        settings.clear()
    else:
        for keyname in keys:
            settings.remove(keyname)


class Diffractometer(object):
    PSI_CONSTANT_MODES = [
        "psi_constant",
        "psi_constant_vertical",
        "psi_constant_horizontal",
    ]

    def __init__(self, name, config):
        self.name = name
        self._config = config
        geometry = config.get("geometry", None)
        if geometry is None:
            raise ValueError("No geometry specified for [{0}]".format(name))
        self._settings = HashObjSetting(name)
        self._geometry = HklGeometry(geometry, self._settings)
        self._motor_calc = None
        self._motor_names = dict()
        register_diffractometer(name, self)

    @property
    def calc_controller(self):
        self._check_motor_calc()
        return self._motor_calc

    @calc_controller.setter
    def calc_controller(self, hklmot):
        self._motor_calc = hklmot
        self._motor_names = dict()
        all_axis = self._motor_calc.reals + self._motor_calc.pseudos
        for axis in all_axis:
            tag = self._motor_calc._axis_tag(axis)
            self._motor_names[tag] = axis.name
        names = self._geometry.get_axis_constant_names("hkl")
        if len(names):
            frozen = self._settings.get("frozen_angles", None)
            if frozen is not None:
                pos = dict(
                    [(name, val) for name, val in frozen.items() if name in names]
                )
                self._motor_calc.frozen_angles = pos

    def _check_motor_calc(self):
        if self._motor_calc is None:
            raise RuntimeError("No HKLMotor controller defined")

    @property
    def geometry_name(self):
        return self._geometry.get_name()

    def get_axis(self, axis_name):
        self._check_motor_calc()
        motor_name = self._motor_names.get(axis_name, None)
        if motor_name is None:
            raise ValueError("Unknown axis name [{0}]".format(axis_name))
        return self._motor_calc.get_axis(motor_name)

    def motor_pos_2_str(self, axis_pos):
        axis_names = self._geometry.get_axis_names()
        hstr = [
            "{0:>10.10s}".format(self._motor_names.get(name, name))
            for name in axis_names
        ]
        vstr = ["{0:10.4f}".format(axis_pos[name]) for name in axis_names]
        return "{0}\n{1}\n".format(" ".join(hstr), " ".join(vstr))

    def pseudo_pos_2_str(self, pos_dict):
        pstr = "H K L = {pos[hkl_h]:f} {pos[hkl_k]:f} {pos[hkl_l]:f}\n".format(
            pos=pos_dict
        )
        for name, value in list(pos_dict.items()):
            if name[0:3] != "hkl":
                pstr += "{0:20s} = {1:f}\n".format(name, value)
        return pstr

    def show_pos(self):
        self._calc_geo()
        print((self.pseudo_pos_2_str(self._geometry.get_pseudo_pos())))
        print((self.motor_pos_2_str(self._geometry.get_axis_pos())))

    def show_ref(self):
        print(self.sample.info(self._motor_names))

    def show_geo(self):
        self._calc_geo()
        print(self._geometry.info(self._motor_names))

    def show(self):
        self.show_geo()

    @property
    def geometry(self):
        return self._geometry

    @property
    def sample(self):
        return self._geometry.get_sample()

    @property
    def motor_names(self):
        self._check_motor_calc()
        return self._motor_names

    @property
    def motor_limits(self):
        self._check_motor_calc()
        lim_dict = dict()
        for name in self.axis_names:
            axis = self.get_axis(name)
            lim_dict[axis.name] = axis.limits
        return lim_dict

    @property
    def geo_limits(self):
        lim_dict = dict()
        for name, value in self._geometry.get_axis_limits().items():
            lim_dict[self._motor_names.get(name, name)] = value
        return lim_dict

    @geo_limits.setter
    def geo_limits(self, lim_dict):
        geo_limits = dict()
        if self._motor_calc is None:
            for name, value in lim_dict.items():
                geo_limits[self.__motor_2_geo_name(name)] = value
        else:
            mot_limits = self.motor_limits
            for name, value in lim_dict.items():
                geo_limits[self.__motor_2_geo_name(name)] = (
                    max(mot_limits[name][0], value[0]),
                    min(mot_limits[name][1], value[1]),
                )
        self._geometry.set_axis_limits(geo_limits)

    def __motor_2_geo_name(self, motor_name):
        for geoname, motname in self._motor_names.items():
            if motname == motor_name:
                return geoname
        if motor_name in self._geometry.get_axis_names():
            return motor_name
        else:
            raise ValueError("[{0}] is not a valid motor name.\n".format(motor_name))

    @property
    def axis_names(self):
        return self._geometry.get_axis_names()

    @property
    def axis_pos(self):
        return self._geometry.get_axis_pos()

    @property
    def pseudo_names(self):
        return self._geometry.get_pseudo_names()

    @property
    def pseudo_pos(self):
        return self._geometry.get_pseudo_pos()

    @property
    def hkl(self):
        self._calc_geo()
        pseudos = self._geometry.get_pseudo_pos()
        hkl = tuple([pseudos[key] for key in ["hkl_h", "hkl_k", "hkl_l"]])
        return hkl

    def check_hkl(self, h, k, l):
        self._geometry.set_pseudo_pos({"hkl_h": h, "hkl_k": k, "hkl_l": l})
        calc_pos = self._geometry.get_axis_pos()
        self._geometry.set_axis_pos(calc_pos)
        calc_pseudo = self._geometry.get_pseudo_pos()
        print("\nCalculated Positions:\n")
        print((self.pseudo_pos_2_str(calc_pseudo)))
        print((self.motor_pos_2_str(calc_pos)))
        self._calc_geo()

    def do_hkl_trajectory(self, hkl1, hkl2, npoints, count_time, interpolation=1):
        self._check_motor_calc()
        print("\n>>> Computes trajectory ...")
        trajectory = self._motor_calc.calc_trajectory(
            ("hkl_h", "hkl_k", "hkl_l"), hkl1, hkl2, npoints, count_time, interpolation
        )
        print(">>> Prepare trajectory ...")
        trajectory.prepare()
        print(">>> Move to start position HKL={0} ...".format(hkl1))
        trajectory.move_to_start()
        print("Start position:")
        self.show_pos()
        print(">>> Move to end position HKL={0} along trajectory ...".format(hkl2))
        trajectory.move_to_end()
        print("End position:")
        self.show_pos()
        print(">>> Done.\n")

    def check_hklscan(self, hkl1, hkl2, npoints):
        axis_names = self._geometry.get_axis_names()
        (h1, k1, l1) = hkl1
        (h2, k2, l2) = hkl2
        errfound = 0
        hstr = [
            "{0:>10.10s}".format(self._motor_names.get(name, name))
            for name in axis_names
        ]
        print(
            ("{0:>8.8s} {1:>8.8s} {2:>8.8s} {3}".format("H", "K", "L", " ".join(hstr)))
        )
        for (h, k, l) in zip(
            numpy.linspace(h1, h2, npoints),
            numpy.linspace(k1, k2, npoints),
            numpy.linspace(l1, l2, npoints),
        ):
            try:
                self._geometry.set_pseudo_pos({"hkl_h": h, "hkl_k": k, "hkl_l": l})
            except:
                print("Cannot compute HKL = ({0}, {1}, {2})".format(h, k, l))
                errfound += 1
                continue
            axis_pos = self._geometry.get_axis_pos()
            pos_str = ["{0:10.4f}".format(axis_pos[name]) for name in axis_names]
            print(("{0:8.4f} {1:8.4f} {2:8.4f} {3}".format(h, k, l, " ".join(pos_str))))
        self._calc_geo()
        if errfound:
            print(
                "\n!!! Failed to compute {0} points (/{1}) !!!".format(
                    errfound, npoints
                )
            )

    def check_lookupscan(self, *motpos):
        pars = list(motpos)
        motnames = list()
        motvalues = list()
        while pars:
            motnames.append(pars.pop(0))
            motvalues.append(pars.pop(0))
        for values in zip(*motvalues):
            pos_dict = dict(zip(motnames, values))
            try:
                self._geometry.set_pseudo_pos(pos_dict)
            except:
                self._calc_geo()
                raise ValueError("Cannot computes geometry for {0}".format(pos_dict))
        self._calc_geo()

    def move_hkl(self, h, k, l):
        self._check_motor_calc()
        h_motor = self._motor_calc.get_axis(self._motor_names["hkl_h"])
        k_motor = self._motor_calc.get_axis(self._motor_names["hkl_k"])
        l_motor = self._motor_calc.get_axis(self._motor_names["hkl_l"])
        group = MotorGroup(h_motor, k_motor, l_motor)
        motor_pos = {h_motor: h, k_motor: k, l_motor: l}
        group.move(motor_pos, wait=True, relative=False)
        calc_pos = self._geometry.get_axis_pos()
        print((self.motor_pos_2_str(calc_pos)))

    def umove_hkl(self, h, k, l):
        self._check_motor_calc()
        axis_names = self._geometry.get_axis_names()
        hstr = [
            "{0:>10.10s}".format(self._motor_names.get(name, name))
            for name in axis_names
        ]
        h_motor = self._motor_calc.get_axis(self._motor_names["hkl_h"])
        k_motor = self._motor_calc.get_axis(self._motor_names["hkl_k"])
        l_motor = self._motor_calc.get_axis(self._motor_names["hkl_l"])
        group = MotorGroup(h_motor, k_motor, l_motor)
        motor_pos = {h_motor: h, k_motor: k, l_motor: l}
        print(("{0}".format(" ".join(hstr))))
        group.move(motor_pos, wait=False, relative=False)
        with error_cleanup(group.stop):
            while group.is_moving:
                axis_pos = self._geometry.get_axis_pos()
                pos_str = ["{0:10.4f}".format(axis_pos[name]) for name in axis_names]
                print_("\r{0}".format(" ".join(pos_str)), end="", flush=True)
                sleep(0.1)

        axis_pos = self._geometry.get_axis_pos()
        pos_str = ["{0:10.4f}".format(axis_pos[name]) for name in axis_names]
        print_("\r{0}".format(" ".join(pos_str)), end="\n", flush=True)

    @property
    def pos(self):
        self._calc_geo()
        axis_pos = self._geometry.get_axis_pos()
        pos = tuple([axis_pos[key] for key in self._geometry.get_axis_names()])
        return pos

    def check_pos(self, *pos):
        axis_names = self._geometry.get_axis_names()
        if len(pos) != len(axis_names):
            raise ValueError(
                "Should gives {0} positions: {1}".format(
                    len(axis_names),
                    " ".join(
                        [self._motor_names.get(name, name) for name in axis_names]
                    ),
                )
            )
        axis_pos = dict(list(zip(axis_names, pos)))
        self._geometry.set_axis_pos(axis_pos)
        calc_pseudo = self._geometry.get_pseudo_pos()
        print("\nCalculated Positions:\n")
        print((self.pseudo_pos_2_str(calc_pseudo)))
        print((self.motor_pos_2_str(axis_pos)))
        self._calc_geo()

    @property
    def energy(self):
        return self._geometry.get_energy()

    @energy.setter
    def energy(self, energy):
        self._geometry.set_energy(energy)

    @property
    def wavelength(self):
        return self._geometry.get_wavelength()

    @wavelength.setter
    def wavelength(self, wavelength):
        self._geometry.set_wavelength(wavelength)

    @property
    def hklmode(self):
        return self._geometry.get_mode("hkl")

    @hklmode.setter
    def hklmode(self, mode):
        prev_mode = self._geometry.get_mode("hkl")
        if mode != prev_mode and self._motor_calc is not None:
            self._motor_calc.unfreeze()
            self._settings["frozen_angles"] = self._motor_calc.frozen_angles
        self._geometry.set_mode("hkl", mode)

    @property
    def hklmode_list(self):
        return self._geometry.get_mode_names()["hkl"]

    @property
    def lattice(self):
        return self.sample.get_lattice()

    @lattice.setter
    def lattice(self, lattice):
        self.sample.set_lattice(*lattice)
        self._calc_UB()
        self._calc_geo()

    @property
    def reciprocal_lattice(self):
        return self.sample.get_reciprocal_lattice()

    @property
    def UB(self):
        return self.sample.get_UB()

    @UB.setter
    def UB(self, ub_array):
        self.sample.set_UB(ub_array)
        self._calc_geo()

    def _calc_UB(self):
        sample = self.sample
        if sample.get_n_reflections() >= 2:
            sample.computeUB()
            print("(UB computed using Busing-Levy)")

    def _calc_geo(self):
        if self._motor_calc is not None:
            self._motor_calc.update()

    @property
    def or0(self):
        if self.sample.get_n_reflections() < 1:
            raise ValueError("Primary reflection not yet defined")
        return self.__ref_get_result(self.sample.get_ref0())

    @or0.setter
    def or0(self, pars):
        (hkl, pos) = self.__ref_get_pars("or0", pars)
        if pos is None:
            self._calc_geo()
            pos = self._geometry.get_axis_pos()
        self.sample.set_ref0(hkl, pos)
        self._calc_UB()
        self._calc_geo()

    @property
    def or1(self):
        if self.sample.get_n_reflections() < 2:
            raise ValueError("Secondary reflection not yet defined")
        return self.__ref_get_result(self.sample.get_ref1())

    @or1.setter
    def or1(self, pars):
        (hkl, pos) = self.__ref_get_pars("or1", pars)
        if pos is None:
            self._calc_geo()
            pos = self._geometry.get_axis_pos()
        self.sample.set_ref1(hkl, pos)
        self._calc_UB()
        self._calc_geo()

    def or_swap(self):
        self.sample.swap_reflections(0, 1)
        self._calc_UB()
        self._calc_geo()

    def __ref_get_result(self, hkl_pos_wl):
        (hkl, pos, wl) = hkl_pos_wl
        return hkl + tuple([pos[name] for name in self.axis_names])

    def __ref_get_pars(self, fname, pars):
        if type(pars) is not tuple:
            raise ValueError(self.__ref_get_usage(fname))
        if len(pars) == 3:
            return (pars, None)
        if len(pars) - 3 != len(self.axis_names):
            raise ValueError(
                "Missing some motor values.\n{0}".format(self.__ref_get_usage(fname))
            )
        pos = dict(list(zip(self.axis_names, pars[3:])))
        return (pars[:3], pos)

    def __ref_get_usage(self, fname):
        if fname.startswith("or"):
            return "Use : {0}.{1}=(H,K,L) or {0}.{1}=({2})".format(
                self.name, fname, ",".join(self.refhead)
            )
        else:
            return "Use : {0}.{1}(H,K,L) or {0}.{1}({2})".format(
                self.name, fname, ",".join(self.refhead)
            )

    def refadd(self, *pars):
        (hkl, pos) = self.__ref_get_pars("addref", pars)
        if pos is None:
            self._calc_geo()
            pos = self._geometry.get_axis_pos()
        self.sample.add_one_reflection(hkl, pos)

    def refdel(self, *index):
        idxlist = list(index)
        idxlist.sort()
        idxlist.reverse()
        for idx in idxlist:
            self.sample.remove_one_reflection(idx)

    @property
    def reflist(self):
        return tuple(map(self.__ref_get_result, self.sample.get_reflections()))

    @reflist.setter
    def reflist(self, reflist):
        self.sample.remove_reflections()
        for ref in reflist:
            pars = self.__ref_get_pars("reflist", ref)
            self.sample.add_one_reflection(*pars)

    @property
    def refhead(self):
        return ("H", "K", "L") + tuple(
            [self.motor_names.get(name, name) for name in self.axis_names]
        )

    def reffit(self):
        sample = self.sample
        nref = sample.get_n_reflections()
        if nref == 2:
            sample.computeUB()
            print("(UB computed using Busing-Levy)")
            self._calc_geo()
        elif nref > 2:
            sample.affine()
            print("(UB computed using {0} reflections)".format(nref))
            self._calc_geo()
        else:
            raise ValueError("Not enough reflections to computes UB !!")

    def refsave(self, filename):
        with open(filename, "w") as reffile:
            reffile.write(
                "#" + tabulate.tabulate(self.reflist, self.refhead, "plain") + "\n"
            )

    def refload(self, filename):
        reflist = list()
        with open(filename, "r") as reffile:
            for line in reffile.readlines():
                if line.startswith("#"):
                    continue
                if len(line.split()) > 3:
                    reflist.append(tuple(map(float, line.split())))
        self.reflist = tuple(reflist)

    def freeze(self, *vals):
        if self.hklmode in self.PSI_CONSTANT_MODES:
            if len(vals):
                psi_value = vals[0]
                self._geometry.set_mode_pars("hkl", self.hklmode, {"psi": psi_value})
            else:
                psi_value = self._geometry.get_mode_pars("hkl", self.hklmode)["psi"]
            print("Freeze psi to {0}".format(psi_value))
        else:
            self._check_motor_calc()
            names = self._geometry.get_axis_constant_names("hkl")
            if not len(names):
                print(
                    (
                        "in hkl [{0}] mode, no constant angles to freeze".format(
                            self._geometry.get_mode("hkl")
                        )
                    )
                )
            else:
                if not len(vals):
                    self._motor_calc.freeze(names)
                    pos_dict = self._motor_calc.frozen_angles
                else:
                    if len(vals) != len(names):
                        raise ValueError(
                            "Missing positions. Should give angles for [{0}]".format(
                                " ".join(names)
                            )
                        )
                    pos_dict = dict(list(zip(names, vals)))
                    self._motor_calc.frozen_angles = pos_dict
                self._settings["frozen_angles"] = pos_dict
                for name, pos in list(pos_dict.items()):
                    print(
                        (
                            "Freeze {0} [{1}] to {2:.4f}".format(
                                self._motor_names[name], name, pos
                            )
                        )
                    )

    def unfreeze(self):
        if self.hklmode in self.PSI_CONSTANT_MODES:
            print("Cannot unfreeze psi in {0} mode.\n".format(self.hklmode))
        else:
            self._check_motor_calc()
            names = list(self._motor_calc.frozen_angles.keys())
            if not len(names):
                print("No frozen angles.\n")
            else:
                for name in names:
                    print(
                        ("Unfreeze {0} [{1}]\n".format(self._motor_names[name], name))
                    )
                self._motor_calc.unfreeze()
                self._settings["frozen_angles"] = self._motor_calc.frozen_angles

    def pr_freeze(self):
        if self.hklmode in self.PSI_CONSTANT_MODES:
            psi_value = self._geometry.get_mode_pars("hkl", self.hklmode)["psi"]
            print("Frozen angles:")
            print("psi = {0:.4f}".format(psi_value))
        else:
            self._check_motor_calc()
            if not len(self._geometry.get_axis_constant_names("hkl")):
                print(
                    "No frozen angles in current hkl mode [{0}].".format(self.hklmode)
                )
            else:
                pos_dict = self._motor_calc.frozen_angles
                if not len(pos_dict):
                    print("No frozen angles defined.")
                else:
                    print("Frozen angles:")
                    for name, pos in list(pos_dict.items()):
                        print(
                            (
                                "{0} [{1}] = {2:.4f}".format(
                                    self._motor_names[name], name, pos
                                )
                            )
                        )

    @property
    def frozen_angles_names(self):
        return self._geometry.get_axis_constant_names("hkl")

    @property
    def frozen_angles(self):
        self._check_motor_calc()
        pos_dict = self._motor_calc.frozen_angles
        return pos_dict
