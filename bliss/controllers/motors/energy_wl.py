"""
Energy/wavelength Bliss controller

monoang: alias for the real monochromator motor
energy: energy calculated axis alias
wavelength: wavelength calculated axis alias
dspace: monochromator crystal d-spacing
"""
from bliss.controllers.motor import CalcController
import math


class energy_wl(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.dspace = self.config.get("dspace", float)

    def calc_from_real(self, positions_dict):
        lamb = 2*self.dspace*math.sin(math.radians(positions_dict["monoang"]))
        return {"energy": 12.3984/lamb, "wavelength": lamb}

    def calc_to_real(self, axis_tag, positions_dict):
        monoangle = math.gedrees(math.asin(12.3984/(positions_dict["energy"]*2*self.dspace)))
        return {"monoang": monoangle}
