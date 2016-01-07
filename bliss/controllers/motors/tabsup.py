"""
Table support Bliss controller

back: alias for real back leg axis
front: alias for real front leg axis
ttrans: Y-axis translation calculated axis alias
trot: Z-axis rotation calculated axis alias


Top view (S=sample position):

         ^  ttrans
         |                            \
         |                             \
------------------------------    trot ^\
    ^                  ^            __/__\
    |          S<-d1-> |
    |             ^    |
    |<---d2--->   |    |
   ^|             |d5  |
 d4||             |    |
   -|             -    |
  back(tyb)      front(tyf)
"""
from bliss.controllers.motor import CalcController
import math


class tabsup(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.d1 = self.config.get("d1", float)
        self.d2 = self.config.get("d2", float)

    def calc_from_real(self, positions_dict):
        tyf = positions_dict["front"]
        tyb = positions_dict["back"]
        d1 = self.d1
        d2 = self.d2

        return {"ttrans": (d1*tyb+d2*tyf)/(d1+d2),
                "trot": math.degrees(math.atan((tyf-tyb)/(d1+d2))) }

    def calc_to_real(self, axis_tag, positions_dict):
        ttrans = positions_dict["ttrans"]
        trot = positions_dict["trot"]
        d1 = self.d1
        d2 = self.d2

        return {"back": ttrans - d2*math.tan(math.radians(trot)),
                "front": ttrans + d1*math.tan(math.radians(trot)) }
