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
        return {"ttrans": (positions_dict["front"] + positions_dict["back"])/2.0,
                "trot": math.degrees((math.atan(positions_dict["back"] - positions_dict["front"]) / self.d * 1000)) }

    def calc_to_real(self, axis_tag, positions_dict):
        return {"back": positions_dict["ttrans"] + self.d * math.tan(math.radians(positions_dict["trot"] / 1000.0)),
                "front": positions_dict["ttrans"]}
