"""
ID31Diffract: ID31 diffractometer calculational controller

Converts the individual decoupled motors of ID31 HEMD and detector stages\
into a six circle diffractometer

real motor tags:
dz1 - upstream table height (mm)
dz2 - downstream table height (mm)
dy - detector translation in y axis (mm)
dtz - detector tilt in z axis (degree)
ai - alpha angle (degree)
lmchi - liquid mode chi (degree)

virtual motor tags:
mu - mu angle (degree)
gamma - gamma angle (degree)
delta - delta angle (degree)
dyo - detector y-offset (mm)
dzo - detector z-offset (mm)
bos - beam offset (mm) (optional, write-only)
ben - beam energy (keV) (optional, write-only)
"""

from numpy import square, sqrt, arctan, arccos, cos, rad2deg, deg2rad

from bliss.config import settings
from bliss.controllers.motor import CalcController
from bliss.controllers.motor import add_axis_method
from bliss.controllers.calculations import ID31_diffractometer
from bliss.common import log

def initialize_parameters(klass, ctrl_pars=None):
    if ctrl_pars is None:
        ctrl_pars = klass.CtrlPars
    def get_param_funcs(name):
        def set_parameter(self, axis, value):
            self[name] = value
        def get_parameter(self, axis):
            return self[name]
        return set_parameter, get_parameter
    for name in ctrl_pars:
        setter, getter = get_param_funcs(name)
        setattr(klass, 'set_%s' % name, setter)
        setattr(klass, 'get_%s' % name, getter)

    orig_initialize_axis = klass.initialize_axis
    def initialize_axis(self, axis):
        orig_initialize_axis(self, axis)
        for name, (ptype, default) in ctrl_pars.items():
            mname = 'set_%s' % name
            method = getattr(self, mname)
            add_axis_method(axis, method, mname, types_info=(ptype, 'None'))
            mname = 'get_%s' % name
            method = getattr(self, mname)
            add_axis_method(axis, method, mname, types_info=('None', ptype))
    klass.initialize_axis = initialize_axis

    return klass


@initialize_parameters
class ID31Diffract(CalcController):

    CtrlPars = {
        'liquid_mode': ('str', 'off'),
        'detector_active': ('bool', False),
        'beam_offset': ('float', 0),
        'beam_energy': ('float', 0),
    }

    ParamMotors = {
        'ben': 'beam_energy',
        'bos': 'beam_offset',
    }

    DetMotors = ['dy', 'dtz', 'dz1', 'dz2']

    def initialize(self, *args, **kws):
        hash_name = 'controller.id31diffract'
        ctrl_name = self.config.get('name', default=None)
        if ctrl_name:
            hash_name += '.%s' % ctrl_name
        self.par_settings = settings.HashSetting(hash_name)
        if not len(self.par_settings):
            for name, (typ, default) in self.CtrlPars.items():
                self.par_settings[name] = default

        self.has_extra = dict([(mot, False) for mot in self.ParamMotors])

        super(ID31Diffract, self).initialize(*args, **kws)

    def initialize_axis(self, axis):
        super(ID31Diffract, self).initialize_axis(axis)
        add_axis_method(axis, self.get_lm_2th, types_info=('None', 'float'))
        tags = axis.config.get('tags').split()
        for mot in self.ParamMotors:
            self.has_extra[mot] |= mot in tags

    def calc_from_real(self, positions_dict):
        phys_pos = dict(positions_dict)
        phys_pos['ai'] = deg2rad(phys_pos['ai'])
        phys_pos['dtz'] = deg2rad(phys_pos['dtz'])
        phys_pos['lmchi'] = deg2rad(phys_pos['lmchi'])

        result = ID31_diffractometer.calc_virt(phys_pos, self)

        result['mu'] = rad2deg(result['mu'])
        result['gamma'] = rad2deg(result['gamma'])
        result['delta'] = rad2deg(result['delta'])
        for mot, par in self.ParamMotors.items():
            if self.has_extra[mot]:
                result[mot] = self[par]
        return result

    def calc_to_real(self, axis_tag, positions_dict):
        virt_pos = dict(positions_dict)
        for mot, par in self.ParamMotors.items():
            curr = self[par]
            if virt_pos.setdefault(mot, curr) != curr:
                self[par] = virt_pos[mot]

        virt_pos['mu'] = deg2rad(virt_pos['mu'])
        virt_pos['gamma'] = deg2rad(virt_pos['gamma'])
        virt_pos['delta'] = deg2rad(virt_pos['delta'])

        result = ID31_diffractometer.calc_phys(virt_pos, self)

        result['ai'] = rad2deg(result['ai'])
        result['dtz'] = rad2deg(result['dtz'])
        result['lmchi'] = rad2deg(result['lmchi'])

        if not self['detector_active']:
            for mot in self.DetMotors:
                result.pop(mot)

        return result

    def get_lm_2th(self, axis):
        lm_2th = ID31_diffractometer.calc_lm_2th(self['liquid_mode'],
                                                 self['beam_energy'])
        return rad2deg(lm_2th)

    def __getitem__(self, name):
        typ_map = dict(liquid_mode=str, detector_active=bool)
        typ = typ_map.setdefault(name, float)
        if name in self.CtrlPars:
            val = self.par_settings[name]
        else:
            val = ID31_diffractometer.Default_Geom_Pars[name]
            val = self.config.get(name, default=val)
        return typ(val)

    def __setitem__(self, name, value):
        if name not in self.CtrlPars:
            raise KeyError, 'Cannot modify read-only config param. %s' % name
        self.par_settings[name] = value


