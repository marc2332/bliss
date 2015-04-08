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
        return {"ttrans": positions_dict["front"] }
        #        "trot": (math.atan(positions_dict["back"] - positions_dict["front"]) / self.d) * 1000}

    def calc_to_real(self, axis_tag, positions_dict):
        current_ttrans = self._tagged["ttrans"][0].position()
        current_front = self._tagged["front"][0].position()
        current_back = self._tagged["back"][0].position()
        delta = positions_dict["ttrans"] - current_ttrans
        return { "back": current_back + delta, "front": current_front + delta }
        #return {"back": positions_dict["ttrans"] + self.d * math.tan(positions_dict["trot"] / 1000.0),
        #        "front": positions_dict["ttrans"]}
