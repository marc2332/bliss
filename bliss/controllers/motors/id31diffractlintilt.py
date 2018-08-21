"""
ID31DiffractLinTilt: transforms linear motors into tilt motor (angular)

Some angular motors are mechanically moved through linear translations.

"""

from numpy import square, sqrt, arctan, arccos, cos, rad2deg, deg2rad

from bliss.controllers.motor import CalcController
from bliss.common.axis import AxisState


class ID31DiffractLinTilt(CalcController):
    def __init__(self, *args, **kwargs):
        super(ID31DiffractLinTilt, self).__init__(*args, **kwargs)

    @property
    def a(self):
        return self.config.get("a", float)

    @property
    def b(self):
        return self.config.get("b", float)

    def c(self, a=None, b=None):
        a = self.a if a is None else a
        b = self.b if b is None else b
        return sqrt(square(a) + square(b))

    def d(self, a=None, b=None):
        a = self.a if a is None else a
        b = self.b if b is None else b
        return arctan(b / a)

    def calc_from_real(self, positions_dict):
        a, b = self.a, self.b
        c, d = self.c(a, b), self.d(a, b)
        a2, c2 = square(a), square(c)
        linear = positions_dict["linear"]
        bc2 = square(b + linear)
        tilt = arccos((a2 + c2 - bc2) / (2 * a * c)) - d
        return dict(tilt=rad2deg(tilt))

    def calc_to_real(self, positions_dict):
        a, b = self.a, self.b
        c, d = self.c(a, b), self.d(a, b)
        a2, c2 = square(a), square(c)
        tilt = deg2rad(positions_dict["tilt"])
        bc = sqrt(a2 + c2 - 2 * a * c * cos(tilt + d))
        linear = bc - b
        return dict(linear=linear)
