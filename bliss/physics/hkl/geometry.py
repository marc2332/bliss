import gi

gi.require_version("Hkl", "5.0")
from gi.repository import Hkl

from .common import *
from .sample import HklSample
from .engine import HklEngine, UsingEngineMode


class HklGeometry(object):
    UNIT = Hkl.UnitEnum.USER
    HC_OVER_E = 12.39842

    def __init__(self, geometry_name, settings=None):
        factory = Hkl.factory_get_by_name(geometry_name)
        if factory is None:
            raise ValueError(
                "Invalid diffractometer geometry name.\n"
                "Known geometries are: {0}".format(get_geometry_list())
            )

        self._geometry = factory.create_new_geometry()
        self._axis_names = self._geometry.axis_names_get()
        self._detector = get_new_detector()
        self._sample = HklSample(self._geometry, self._detector, settings)

        self._engine_list = factory.create_new_engine_list()
        self._init_engines()

        self._axis_limits_init = dict()

        if settings is None:
            self._settings = dict()
        else:
            self._settings = settings
            self._init_settings()

        self.update()

    def _init_settings(self):
        wavelength = self._settings.get("wavelength", None)
        if wavelength is not None:
            self._geometry.wavelength_set(wavelength, self.UNIT)
        for engname, engine in list(self._engines.items()):
            engmodes = engine.get_modes()
            if len(engmodes) > 1:
                modekey = "{0}_mode".format(engname)
                modeval = self._settings.get(modekey, None)
                if modeval is not None:
                    engine.set_current_mode(modeval)
            for modename in engmodes:
                parskey = "{0}_{1}_pars".format(engname, modename)
                parsval = self._settings.get(parskey, None)
                if parsval is not None:
                    self.set_mode_pars(engname, modename, parsval)
        axislimits = dict()
        for axisname in self._axis_names:
            limkey = "{0}_limits".format(axisname)
            limval = self._settings.get(limkey, None)
            if limval is not None:
                axislimits[axisname] = limval
        if len(axislimits):
            self.set_axis_limits(axislimits)

    def _init_engines(self):
        self._engine_list.init(
            self._geometry, self._detector, self._sample.get_sample()
        )
        self._engines = dict()
        for engine in self._engine_list.engines_get():
            name = engine.name_get()
            self._engines[name] = HklEngine(engine)

    def get_engine(self, engine_name=None):
        engine = self._engines.get(engine_name, None)
        if engine is None:
            raise ValueError("Invalid engine name [{0}]".format(engine_name))
        return engine

    def get_engine_names(self):
        return list(self._engines.keys())

    def get_engine_from_pseudo_tag(self, tag):
        return self.__alias_to_pseudo(tag)[0]

    def get_mode_names(self):
        modes = dict()
        for name, engine in list(self._engines.items()):
            modes[name] = engine.get_modes()
        return modes

    def set_mode(self, engine_name, mode_name):
        engine = self.get_engine(engine_name)
        engine.set_current_mode(mode_name)
        self._settings["{0}_mode".format(engine_name)] = mode_name

    def get_mode(self, engine_name):
        engine = self.get_engine(engine_name)
        return engine.get_current_mode()

    def get_mode_pars(self, engine_name, mode_name):
        engine = self.get_engine(engine_name)
        with UsingEngineMode(engine, mode_name):
            pars = engine.get_parameters()
        return pars

    def set_mode_pars(self, engine_name, mode_name, pars_dict):
        engine = self.get_engine(engine_name)
        with UsingEngineMode(engine, mode_name):
            engine.set_parameters(pars_dict)
        self._settings["{0}_{1}_pars".format(engine_name, mode_name)] = pars_dict

    def mode_has_pars(self, engine_name, mode_name):
        engine = self.get_engine(engine_name)
        with UsingEngineMode(engine, mode_name):
            has_pars = engine.has_parameters()
        return has_pars

    def mode_is_read_only(self, engine_name, mode_name):
        engine = self.get_engine(engine_name)
        with UsingEngineMode(engine, mode_name):
            is_read_only = engine.is_read_only()
        return is_read_only

    def get_name(self):
        return self._geometry.name_get()

    def get_sample(self):
        return self._sample

    def get_wavelength(self):
        """ wavelength in angstrom """
        return self._geometry.wavelength_get(self.UNIT)

    def set_wavelength(self, wavelength):
        self._geometry.wavelength_set(wavelength, self.UNIT)
        self._settings["wavelength"] = wavelength
        self.update()

    def get_energy(self):
        """ Returns energy in KeV """
        wavelength = self.get_wavelength()
        energy = self.HC_OVER_E / wavelength
        return energy

    def set_energy(self, energy):
        wavelength = self.HC_OVER_E / energy
        self.set_wavelength(wavelength)

    def __get_axis(self, axis_name):
        if axis_name not in self._axis_names:
            raise ValueError(
                "Invalid diffractometer axis name.\n"
                "Possible axis are : {0}".format(" ".join(self._axis_names))
            )
        return self._geometry.axis_get(axis_name)

    # ======= Warning limits are Geo limits (not the real motors limits) =========

    def is_axis_limits_initialized(self, axis_name):
        return self._axis_limits_init.get(axis_name, False)

    def set_axis_limits(self, axis_limits):
        for axis_name, (axis_min, axis_max) in list(axis_limits.items()):
            axis = self.__get_axis(axis_name)
            axis.min_max_set(axis_min, axis_max, self.UNIT)
            self._geometry.axis_set(axis_name, axis)
            self._axis_limits_init[axis_name] = True
            self._settings["{0}_limits".format(axis_name)] = (axis_min, axis_max)

    def get_axis_limits(self):
        axis_limits = dict()
        for axis_name in self._axis_names:
            axis = self.__get_axis(axis_name)
            (axis_min, axis_max) = axis.min_max_get(self.UNIT)
            axis_limits[axis_name] = (axis_min, axis_max)
        return axis_limits

    def get_axis_units(self):
        axis_units = dict()
        for axis_name in self._axis_names:
            axis = self._geometry.axis_get(axis_name)
            axis_units[axis_name] = axis.user_unit_get()
        return axis_units

    def get_axis_names(self):
        return self._axis_names

    def get_axis_pos(self):
        return get_geometry_positions(self._geometry, self.UNIT)

    def set_axis_pos(self, pos_dict, update=True):
        set_geometry_positions(self._geometry, pos_dict, self.UNIT)
        if update is True:
            self.update()

    def update(self):
        """ will computes pseudo positions on all engines """
        self._engine_list.get()

    def get_axis_constant_names(self, engine_name):
        engine = self.get_engine(engine_name)
        return engine.get_axis_constant_names()

    def get_axis_involved(self, *pseudo_names):
        engine_name = None
        for alias in pseudo_names:
            (engname, _) = self.__alias_to_pseudo(alias)
            if engine_name is None:
                engine_name = engname
            else:
                if engname != engine_name:
                    raise ValueError(
                        "Cannot mix engines {0} and {1}".format(engine_name, engname)
                    )
        engine = self._engines[engine_name]
        return engine.get_axis_write_names()

    def get_pseudo_names(self):
        pseudo_names = list()
        for engname, engine in list(self._engines.items()):
            for name in engine.get_pseudo_names():
                pseudo_names.append(self.__pseudo_to_alias(engname, name))
        return pseudo_names

    def __pseudo_to_alias(self, engname, name):
        return "{0}_{1}".format(engname, name)

    def __alias_to_pseudo(self, alias):
        pars = alias.split("_")
        if len(pars) >= 2:
            (engname, name) = ("_".join(pars[:-1]), pars[-1])
        else:
            raise ValueError("Invalid pseudo name [{0}]".format(alias))
        if engname not in list(self._engines.keys()):
            raise ValueError("Invalid engine name in alias [{0}]".format(alias))
        if name not in self._engines[engname].get_pseudo_names():
            raise ValueError("Invalid pseudo name in alias [{0}]".format(alias))
        return (engname, name)

    def get_pseudo_pos(self):
        pseudo_pos = dict()
        for engname, engine in list(self._engines.items()):
            eng_pos = engine.get_pseudo_pos()
            for name, pos in list(eng_pos.items()):
                pseudo_pos[self.__pseudo_to_alias(engname, name)] = pos
        return pseudo_pos

    def set_pseudo_pos(self, pos_dict):
        """ set the postion of pseudo axes (from same engine).
            pos_dict: {pseudoname: position, ...}

            Mixing axes from different engines is not allowed to ensure
            the unicity of the solution. 

            Returns the closest solution among all solutions proposed by the concerned engine. 
        """

        engine_name = None
        engine_pos = dict()
        for alias, pos in list(pos_dict.items()):
            (engname, name) = self.__alias_to_pseudo(alias)
            if engine_name is None:
                engine_name = engname
            else:
                if engname != engine_name:
                    raise ValueError(
                        "Cannot mix engines {0} and {1}".format(engine_name, engname)
                    )
            engine_pos[name] = pos_dict[alias]

        engine = self._engines[engine_name]
        if engine.is_read_only():
            raise ValueError("Cannot set pseudo on engine [{0}]".format(engine_name))
        solutions = engine.set_pseudo_pos(engine_pos)
        axis_pos = self.__select_solution(solutions)
        set_geometry_positions(self._geometry, axis_pos, self.UNIT)

    def __select_solution(self, solutions):
        """ Solutions are sorted by distance to current pos.
            Here we take the first one (closest one)
            Note that these solutions already take into account the geo limits (init as default to motor limits).
         """
        return solutions[0]

    def get_all_pos(self):
        pos = dict()
        pos.update(self.get_axis_pos())
        pos.update(self.get_pseudo_pos())
        return pos

    def get_sample_rotation(self):
        rot = self._geometry.sample_rotation_get(self._sample.get_sample())
        return matrix_to_numpy(rot.to_matrix())

    def get_detector_rotation(self):
        rot = self._geometry.detector_rotation_get(self._detector)
        return matrix_to_numpy(rot.to_matrix())

    def info(self, mapnames=None):
        if mapnames is None:
            mapnames = {}
        msg = "GEOMETRY : {0}\n".format(self.get_name())
        msg += "ENERGY : {0} KeV\n".format(self.get_energy())
        msg += "PHYSICAL AXIS :\n"
        axis_units = self.get_axis_units()
        axis_limits = self.get_axis_limits()
        axis_pos = self.get_axis_pos()
        for name in self._axis_names:
            msg += " - {0:8.8s} [{1:8.8s}] = {2:8.4f} {3:6.6s} limits= ({4},{5})\n".format(
                name,
                mapnames.get(name, "no-motor"),
                axis_pos[name],
                axis_units[name],
                *axis_limits[name]
            )
        msg += "\nMODES : \n"
        msg += " {0:10s}      - {1:30.30s} {2}\n".format(
            "--engine--", "--mode--", "{ --parameters-- }"
        )
        for engname, engine in list(self._engines.items()):
            currmode = engine.get_current_mode()
            for name in engine.get_modes():
                msg += " {0:10s} [{1}] {2} {3:30.30s}".format(
                    engname.upper(),
                    engine.is_read_only() and "RO" or "RW",
                    name == currmode and "*" or " ",
                    name,
                )
                if self.mode_has_pars(engname, name):
                    msg += " {0}".format(self.get_mode_pars(engname, name))
                msg += "\n"
        msg += "\nPSEUDO AXIS :\n"
        msg += " {0:10s} - {1:10s} [{2:8s}]\n".format(
            "--engine--", "--name--", "-motor-"
        )
        pseudo_pos = self.get_pseudo_pos()
        for engname, engine in list(self._engines.items()):
            for name in engine.get_pseudo_names():
                alias = self.__pseudo_to_alias(engname, name)
                motname = mapnames.get(alias, "")
                if motname == alias:
                    motname = ""
                msg += " {0:10s} - {1:10s} [{2:8s}] = {3:8.4f}\n".format(
                    engname.upper(), name, motname, pseudo_pos[alias]
                )
        return msg
