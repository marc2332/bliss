"""
3-legs table Bliss controller

back1, back2: aliases for real back legs axes
front: alias for real front leg axis
z: alias for calculated height axis
xtilt: alias for calculated tilt axis aligned in beam direction
ytilt: alias for calculated vertical tilt axis
d1: distance between 2 back legs
d2: distance between front leg and middle point between back legs
d3: (depends on geometry) distance between front leg and reference height point
geometry: number 0..7
"""
from bliss.controllers.motor import CalcController
import math

class tab3(CalcController):

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.geometry = self.config.get("geometry", int)
        self.d1 = self.config.get("d1", float)
        self.d2 = self.config.get("d2", float)
        if self.geometry == 5:
            self.d3 = self.config.get("d3", float)

    def calc_from_real(self, positions_dict):
        xtilt = math.atan((positions_dict["back2"] - positions_dict["back1"]) / self.d1)
        if self.geometry in (1, 2):
            back = positions_dict["back1"]
        else:
            back = (positions_dict["back1"] + positions_dict["back2"]) / 2
        ytilt = math.atan((back - positions_dict["front"]) / self.d2)
        if self.geometry in (2, 6):
            xtilt, ytilt = map(math.degrees, (xtilt, ytilt))
        else:
            xtilt = 1000*xtilt
            ytilt = 1000*ytilt
        back = (positions_dict["back1"] + positions_dict["back2"]) / 2
        front = positions_dict["front"]
        if self.geometry == 1:
            back = positions_dict["back2"]
        elif self.geometry == 2:
            back = positions_dict["back1"]
        elif self.geometry in (3, 6):
            front = back
        else:
            back = (positions_dict["back1"] + positions_dict["back2"]) / 2
        if self.geometry == 5:
            z = front + ((back-front) * self.d3 / self.d2)
        else:
            z = (front + back) / 2

        return { "z": z,
                 "xtilt": xtilt,
                 "ytilt": ytilt }

    def calc_to_real(self, axis_tag, positions_dict):
        if self.geometry in (2, 6):
            xtan = math.tan(math.radians(positions_dict["xtilt"]))
            ytan = math.tan(math.radians(positions_dict["ytilt"]))
        else:
            xtan = math.tan(positions_dict["xtilt"]/1000)
            ytan = math.tan(positions_dict["ytilt"]/1000)
        d1 = self.d1 / 2
        if self.geometry in (3, 6):
            d3 = self.d2
            dback = 0
        elif self.geometry == 5:
            d3 = self.d3
            dback = self.d2 - self.d3
        else:
            d3 = self.d2 / 2
            dback = d3
        
        if self.geometry == 4:
            front = positions_dict["z"] + (d3 * ytan)
        elif self.geometry == 1:
            front = positions_dict["z"] + (d3 * ytan) - (d1 * xtan)
        else:
            front = positions_dict["z"] - (d3 * ytan)
        
        if self.geometry in (1, 4):
            sign = -1
        else:
            sign = 1
        if self.geometry == 2:
            back1 = positions_dict["z"] + (dback * ytan)
        else:
            back1 = positions_dict["z"] - (d1 * xtan) + (sign * dback * ytan)
        back2 = positions_dict["z"] + (d1 * xtan) + (sign * dback * ytan)
        
        return { "back1": back1, 
                 "back2": back2, 
                 "front": front }
