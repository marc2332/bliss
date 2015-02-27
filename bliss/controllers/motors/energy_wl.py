"""
Energy/wavelength Bliss controller

monoang: alias for the real monochromator motor
energy: energy calculated axis alias
wavelength: wavelength calculated axis alias
dspace: monochromator crystal d-spacing
"""

from bliss.controllers.motor import CalcController; from bliss.common import event
import math


class energy_wl(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.axis_settings.add("dspace", float)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        event.connect(axis, "dspace", self._calc_from_real)

    def calc_from_real(self, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        # NB: lambda is a keyword.
        lamb = 2 * dspace * math.sin(math.radians(positions_dict["monoang"]))
        return {"energy": 12.3984 / lamb, "wavelength": lamb}

    def calc_to_real(self, axis_tag, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        monoangle = math.degrees(math.asin(12.3984 / (positions_dict["energy"] * 2 * dspace)))
        return {"monoang": monoangle}
