
import gi

gi.require_version("Hkl", "5.0")
from gi.repository import Hkl

from .common import get_geometry_positions


class UsingEngineMode(object):
    """Context manager that sets a temporary mode on engine"""

    def __init__(self, engine, mode):
        self.engine = engine
        self.mode = mode

    def __enter__(self):
        self.current = self.engine.get_current_mode()
        if self.mode != self.current:
            self.engine.set_current_mode(self.mode)

    def __exit__(self, type_, value, traceback):
        if self.mode != self.current:
            self.engine.set_current_mode(self.current)


class HklEngine(object):
    UNIT = Hkl.UnitEnum.USER

    def __init__(self, engine):
        self._engine = engine
        self._has_parameters = len(self._engine.parameters_names_get()) > 0
        self._is_read_only = len(self.get_axis_write_names()) == 0
        if self._engine.capabilities_get() & Hkl.EngineCapabilities.INITIALIZABLE:
            self._need_init = True
        else:
            self._need_init = False
        self._solutions = list()

    def get_name(self):
        return self._engine.name_get()

    def get_modes(self):
        return self._engine.modes_names_get()

    def get_current_mode(self):
        return self._engine.current_mode_get()

    def set_current_mode(self, mode_name):
        self._engine.current_mode_set(mode_name)
        self._has_parameters = len(self._engine.parameters_names_get()) > 0
        self._is_read_only = len(self.get_axis_write_names()) == 0

    def is_read_only(self):
        return self._is_read_only

    def has_parameters(self):
        return self._has_parameters

    def get_parameters(self):
        if not self._has_parameters:
            return dict()
        names = self._engine.parameters_names_get()
        values = self._engine.parameters_values_get(self.UNIT)
        pars = dict()
        for name, val in zip(names, values):
            pars[name] = val
        return pars

    def set_parameters(self, par_dict):
        if not self._has_parameters:
            raise ValueError(
                "Current mode [{0}] has no parameters".format(self.get_current_mode())
            )
        names = self._engine.parameters_names_get()
        values = self._engine.parameters_values_get(self.UNIT)
        for name, val in list(par_dict.items()):
            try:
                idx = names.index(name)
            except:
                raise ValueError(
                    "Invalid parameter [{0}] for mode [{1}]".format(
                        name, self.get_current_mode()
                    )
                )
            values[idx] = val
        self._engine.parameters_values_set(values, self.UNIT)

    def get_pseudo_names(self):
        return self._engine.pseudo_axis_names_get()

    def get_pseudo_pos(self):
        names = self._engine.pseudo_axis_names_get()
        values = self._engine.pseudo_axis_values_get(self.UNIT)
        pos = dict()
        for (name, val) in zip(names, values):
            pos[name] = val
        return pos

    def set_pseudo_pos(self, pos_dict):
        if self._is_read_only:
            raise ValueError("Cannot set pseudo with current mode")
        names = self._engine.pseudo_axis_names_get()
        values = self._engine.pseudo_axis_values_get(self.UNIT)
        for (name, pos) in list(pos_dict.items()):
            try:
                idx = names.index(name)
            except ValueError:
                raise ValueError("Invalid pseudo name [{0}].".format(name))
            values[idx] = pos
        if self._need_init:
            self._engine.initialized_set(True)
        solutions_list = self._engine.pseudo_axis_values_set(values, self.UNIT)
        self._solutions = list()
        for geo_item in list(solutions_list.items()):
            geometry = geo_item.geometry_get()
            self._solutions.append(get_geometry_positions(geometry, self.UNIT))
        return self._solutions

    def get_solutions(self):
        return self._solutions

    def get_axis_write_names(self):
        return self._engine.axis_names_get(Hkl.EngineAxisNamesGet.WRITE)

    def get_axis_read_names(self):
        return self._engine.axis_names_get(Hkl.EngineAxisNamesGet.READ)

    def get_axis_constant_names(self):
        w_axis = self.get_axis_write_names()
        r_axis = self.get_axis_read_names()
        c_axis = [name for name in r_axis if name not in w_axis]
        return c_axis
