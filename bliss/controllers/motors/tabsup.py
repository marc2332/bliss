"""
Table support Bliss controller

back: alias for real back leg axis
front: alias for real front leg axis
ttrans: translation calculated axis alias
trot: rotation calculated axis alias
d: distance between the 2 actuators

         ^  ttrans
         |                    \
         |                     \
----------------------    trot ^\
    ^         ^             __/__\
    |         |
    |         |
    |<---d--->|
    |         |
   back      front

"""
from bliss.controllers.motor import CalcController
import math


class tabsup(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.d = self.config.get("d", float)

    def calc_from_real(self, positions_dict):
        front, back = positions_dict["front"], positions_dict["back"]
        return {"ttrans": (front + back) / 2.,
                "trot": math.degrees(math.atan(float(front - back) / self.d)) }

    def calc_to_real(self, axis_tag, positions_dict):
        ttrans, trot = positions_dict["ttrans"], positions_dict["trot"]
        d2_tg = self.d / 2. * math.tan(math.radians(trot))
        return {"back": ttrans - d2_tg,
                "front": ttrans + d2_tg }

