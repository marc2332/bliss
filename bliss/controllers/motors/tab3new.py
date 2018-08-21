"""
3-leg table

"""
from bliss.controllers.motor import CalcController
from bliss.controllers.motors.threelegtable.InvKin import invKin
from bliss.controllers.motors.threelegtable.FwdKin import fwdKin
from bliss.controllers.motors.threelegtable.Leg import Leg
import math
import numpy


class Sample(object):
    pass


class tab3new(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self._legs = []

    def calc_from_real(self, positions_dict):
        front = positions_dict["front"]
        back1 = positions_dict["back1"]
        back2 = positions_dict["back2"]

        if not self._legs:
            for leg in ("front", "back1", "back2"):
                leg_config = self.config.get(leg + "_leg", dict)

                new_leg = Leg(leg_config["dof"])
                new_leg.w = leg_config["world"]
                new_leg.s = leg_config["sample"]
                self._legs.append(new_leg)

        for i, leg in enumerate(("front", "back1", "back2")):
            self._legs[i].u = positions_dict.get(leg)

        [z, rx, ry, rz] = fwdKin(*self._legs)

        return {"z": z, "xtilt": rx, "ytilt": ry}

    def calc_to_real(self, positions_dict):
        xtilt = positions_dict["xtilt"]
        ytilt = positions_dict["ytilt"]
        z = positions_dict["z"]

        sample = Sample()
        sample.z = z
        sample.rx = xtilt
        sample.ry = ytilt

        [l1, l2, l3] = invKin(self._legs[0], self._legs[1], self._legs[2], sample)

        return {"back1": l2.u, "back2": l3.u, "front": l1.u}
